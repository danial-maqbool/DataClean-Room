"""Bounded custom-literal candidates for OCR text only.

Exact text detectors stay unchanged. Approximate candidates cover whole OCR
words, never arbitrary substrings of longer identifiers. All candidates are
masked conservatively. Edit distance and OCR scores are not probabilities.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from localdesk.safety import InputError
from .detectors import detect

MIN_FUZZY_LENGTH = 8
MAX_CANDIDATES = 6000
MAX_COMPARISONS = 200_000
MAX_DISTANCE_CELLS = 2_000_000


def normalized(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum()
    )


class Budget:
    def __init__(self):
        self.comparisons = 0
        self.cells = 0

    def compare(self):
        self.comparisons += 1
        if self.comparisons > MAX_COMPARISONS:
            raise InputError(
                "OCR matching reached its comparison limit. Split the input or use reviewed manual masks."
            )

    def spend(self, cells):
        self.cells += cells
        if self.cells > MAX_DISTANCE_CELLS:
            raise InputError(
                "OCR matching reached its distance limit. Split the input or use reviewed manual masks."
            )


def distance(a: str, b: str, limit: int, budget: Budget) -> int:
    """Return a banded Levenshtein distance, or limit + 1 when out of range."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    while a and b and a[0] == b[0]:
        a, b = a[1:], b[1:]
    while a and b and a[-1] == b[-1]:
        a, b = a[:-1], b[:-1]
    if not a or not b:
        return min(limit + 1, max(len(a), len(b)))
    previous = {j: j for j in range(min(len(b), limit) + 1)}
    for i, ca in enumerate(a, 1):
        first, last = max(1, i - limit), min(len(b), i + limit)
        budget.spend(last - first + 1)
        row = {0: i} if i <= limit else {}
        for j in range(first, last + 1):
            row[j] = min(
                previous.get(j, limit + 1) + 1,
                row.get(j - 1, limit + 1) + 1,
                previous.get(j - 1, limit + 1) + (ca != b[j - 1]),
            )
        if min(row.values(), default=limit + 1) > limit:
            return limit + 1
        previous = row
    return min(limit + 1, previous.get(len(b), limit + 1))


def confidence(words):
    scores = [w.get("confidence") for w in words]
    if any(
        isinstance(s, bool)
        or not isinstance(s, (int, float))
        or not math.isfinite(s)
        or not 0 <= s <= 100
        for s in scores
    ):
        return None
    return min(scores) if scores else None


def _runs(document, page):
    """Keep nearby OCR words together. Never cross native text, columns or pages."""
    run, previous = [], None
    for word in sorted(page["words"], key=lambda w: w["start"]):
        if "confidence" not in word:
            if run:
                yield run
            run, previous = [], None
            continue
        box = word["bbox"]
        if (
            len(box) != 4
            or not all(
                isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
                for v in box
            )
            or not 0 <= box[0] < box[2] <= math.ceil(page["width"]) + 1
            or not 0 <= box[1] < box[3] <= math.ceil(page["height"]) + 1
        ):
            raise InputError("OCR returned invalid word coordinates.")
        if (
            any(
                isinstance(word.get(k), bool) or not isinstance(word.get(k), int)
                for k in ("start", "end")
            )
            or not 0 <= word["start"] < word["end"] <= len(document["text"])
            or document["text"][word["start"] : word["end"]] != word["text"]
        ):
            raise InputError("OCR returned invalid text positions.")
        if previous:
            a = previous.get("match_bbox", previous["bbox"])
            b = word.get("match_bbox", box)
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            height = max(1, min(a[3] - a[1], b[3] - b[1]))
            gap = b[0] - a[2]
            between = document["text"][previous["end"] : word["start"]]
            if (
                overlap < height * 0.5
                or b[0] < a[0]
                or gap > max(20, height * 2)
                or between.strip()
                or word.get("orientation", 0) != previous.get("orientation", 0)
            ):
                if run:
                    yield run
                run = []
        # Keep offsets in the original string even when Unicode normalization expands it.
        for part in re.finditer(r"\w+", word["text"]):
            value = normalized(part.group())
            if value:
                run.append(
                    (
                        value,
                        word["start"] + part.start(),
                        word["start"] + part.end(),
                        word,
                    )
                )
        previous = word
    if run:
        yield run


def document_matches(document: dict, *, enabled=None, literals=None):
    """Return exact matches, extra OCR candidates, and value-free review metadata."""
    text = document["text"]
    matches = detect(text, enabled=enabled, literals=literals)
    rules = literals or []
    active = enabled is None or "custom" in enabled
    review = {
        "algorithm": "ocr-literal-v1",
        "candidates": [],
        "unmatched_rule_ids": [],
        "short_or_repetitive_rule_ids": [],
        "unresolved_pages": list(document.get("unresolved_ocr_pages", [])),
        "requires_confirmation": False,
        "scores_are_probabilities": False,
    }
    if not active or not rules:
        return matches, review
    found = {
        i for i, value in enumerate(rules, 1) if re.search(re.escape(value), text, re.I)
    }
    budget = Budget()
    seen = set()
    exact = list(matches)
    for page in document["pages"]:
        runs = list(_runs(document, page))
        for rule_id, literal in enumerate(rules, 1):
            target = normalized(literal)
            if len(target) < MIN_FUZZY_LENGTH or len(set(target)) < 4:
                if rule_id not in review["short_or_repetitive_rule_ids"]:
                    review["short_or_repetitive_rule_ids"].append(rule_id)
                continue
            limit = 1 if len(target) < 16 else 2
            target_chars = Counter(target)
            for run in runs:
                for start in range(len(run)):
                    candidate, used = "", []
                    for end in range(start, len(run)):
                        value, _, stop, word = run[end]
                        candidate += value
                        used.append(word)
                        if len(candidate) > len(target) + limit:
                            break
                        if len(candidate) < len(target) - limit:
                            continue
                        budget.compare()
                        # Necessary character-count bound, not a heuristic acceptance rule.
                        counts = Counter(candidate)
                        if (
                            max(
                                sum((target_chars - counts).values()),
                                sum((counts - target_chars).values()),
                            )
                            > limit
                        ):
                            continue
                        edits = distance(target, candidate, limit, budget)
                        if edits > limit:
                            continue
                        first = run[start][1]
                        found.add(rule_id)
                        key = (page["page"], first, stop, rule_id)
                        if key in seen:
                            continue
                        seen.add(key)
                        if all(
                            any(
                                w["start"] < m["end"] and m["start"] < w["end"]
                                for m in exact
                            )
                            for w in used
                        ):
                            # Skip only when exact matches already mask every contributing word.
                            continue
                        method = "normalized" if edits == 0 else "edit-distance"
                        detail = {
                            "rule_id": rule_id,
                            "page": page["page"],
                            "start": first,
                            "end": stop,
                            "method": method,
                            "edits": edits,
                            "ocr_confidence": confidence(used),
                            "review_required": True,
                        }
                        review["candidates"].append(detail)
                        matches.append(
                            {
                                "kind": "custom",
                                "start": first,
                                "end": stop,
                                "value": text[first:stop],
                                "ocr_candidate": True,
                            }
                        )
                        if len(matches) > MAX_CANDIDATES:
                            raise InputError(
                                "Too many OCR redaction candidates. Split the input."
                            )
    review["unmatched_rule_ids"] = [
        i for i in range(1, len(rules) + 1) if i not in found
    ]
    # Do not silently export an OCR document when a requested value was never located.
    review["requires_confirmation"] = bool(
        review["unmatched_rule_ids"] or review["unresolved_pages"]
    )
    return sorted(matches, key=lambda m: (m["start"], m["end"])), review


def review_warnings(review):
    warnings = []
    if review["candidates"]:
        warnings.append(
            "OCR near-matches were included in the masks. They can include harmless text. Review the marked regions. OCR scores and edit distances are not removal guarantees."
        )
        if any(
            c["ocr_confidence"] is None or c["ocr_confidence"] < 60
            for c in review["candidates"]
        ):
            warnings.append(
                "Some OCR candidates have low or unavailable recognition scores. Their masks were retained, not discarded. Check the source and exported pixels."
            )
    if review["unmatched_rule_ids"]:
        warnings.append(
            "OCR did not locate custom rule(s) "
            + ", ".join(map(str, review["unmatched_rule_ids"]))
            + ". Add manual masks or verify that the values are absent. Explicit review confirmation is required to export."
        )
    if review["unresolved_pages"]:
        warnings.append(
            "Orientation checks did not locate a custom value on page(s) "
            + ", ".join(map(str, review["unresolved_pages"]))
            + ". Review those pages before export."
        )
    if review["short_or_repetitive_rule_ids"]:
        warnings.append(
            "Short or repetitive custom values use exact matching only. Review their image regions manually."
        )
    return warnings


def require_review(review, confirmed):
    if not isinstance(confirmed, bool):
        raise InputError("OCR review confirmation must be true or false.")
    if review["requires_confirmation"] and not confirmed:
        raise InputError(
            "OCR could not locate every requested custom value. Add manual masks or verify absence, then confirm the OCR review before export."
        )
