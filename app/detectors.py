"""Deterministic privacy patterns with explicit coverage and overlap handling.

These are review aids, not proof that a file contains no private information.
Names and addresses require labels or user-supplied literal values.
"""

from __future__ import annotations
import ipaddress
import re
from collections import Counter
from localdesk.safety import InputError

KINDS = {
    "email": "Email address",
    "phone": "Phone-like number",
    "cnic": "CNIC-like number",
    "card": "Luhn-valid card-like number",
    "ipv4": "IPv4 address",
    "iban": "IBAN",
    "name": "Labeled name",
    "address": "Labeled address",
    "custom": "Custom private text",
}
PRIORITY = {
    "custom": 0,
    "address": 1,
    "name": 2,
    "email": 3,
    "iban": 4,
    "card": 5,
    "cnic": 6,
    "ipv4": 7,
    "phone": 8,
}
PATTERNS = {
    "email": re.compile(
        r"(?<![\w.+-])[A-Z0-9._%+-]{1,64}@[A-Z0-9.-]{1,190}\.[A-Z]{2,30}(?![\w.-])",
        re.I,
    ),
    "cnic": re.compile(r"(?<!\d)\d{5}-\d{7}-\d(?!\d)"),
    "card": re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
    "ipv4": re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
    "phone": re.compile(r"(?<![\w])\+?\d[\d ()+.-]{6,24}\d(?![\w])"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"),
    "name": re.compile(
        r"^(?:full name|name|patient|customer)\s*:\s*([^\r\n]{2,120})", re.I | re.M
    ),
    "address": re.compile(
        r"^(?:home address|postal address|address)\s*:\s*([^\r\n]{5,200})", re.I | re.M
    ),
}


def luhn(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit() and c.isascii()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) < 2:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def valid_iban(value: str) -> bool:
    text = value.replace(" ", "")
    if not 15 <= len(text) <= 34:
        return False
    rotated = text[4:] + text[:4]
    numeric = "".join(str(ord(c) - 55) if "A" <= c <= "Z" else c for c in rotated)
    return numeric.isdigit() and int(numeric) % 97 == 1


def detect(
    text: str, *, enabled: list[str] | None = None, literals: list[str] | None = None
) -> list[dict]:
    if len(text) > 250_000:
        raise InputError("Text scan input exceeds 250,000 characters.")
    enabled = list(KINDS) if enabled is None else enabled
    if not isinstance(enabled, list) or any(k not in KINDS for k in enabled):
        raise InputError("A selected privacy detector does not exist.")
    literals = literals or []
    if (
        not isinstance(literals, list)
        or len(literals) > 30
        or any(not isinstance(s, str) or not 1 <= len(s) <= 200 for s in literals)
    ):
        raise InputError("Use up to 30 custom values, each 1 to 200 characters long.")
    candidates = []
    for kind, pattern in PATTERNS.items():
        if kind not in enabled:
            continue
        for match in pattern.finditer(text):
            start, end = match.span(1 if kind in {"name", "address"} else 0)
            value = text[start:end]
            if kind == "card" and not luhn(value):
                continue
            if kind == "iban" and not valid_iban(value):
                continue
            if kind == "ipv4":
                try:
                    ipaddress.IPv4Address(value)
                except ipaddress.AddressValueError:
                    continue
            if kind == "phone":
                digits = re.sub(r"\D", "", value)
                if not 9 <= len(digits) <= 15 or re.fullmatch(
                    r"\d{4}[.-]\d{2}[.-]\d{2}", value
                ):
                    continue
            candidates.append(
                {"kind": kind, "start": start, "end": end, "value": value}
            )
            if len(candidates) > 6000:
                raise InputError(
                    "This document has too many candidate matches. Split the input."
                )
    if "custom" in enabled:
        for literal in literals:
            for match in re.finditer(re.escape(literal), text, re.I):
                candidates.append(
                    {
                        "kind": "custom",
                        "start": match.start(),
                        "end": match.end(),
                        "value": match.group(),
                    }
                )
                if len(candidates) > 6000:
                    raise InputError(
                        "This document has too many custom matches. Split the input."
                    )
    accepted = []
    for match in sorted(
        candidates,
        key=lambda m: (PRIORITY[m["kind"]], -(m["end"] - m["start"]), m["start"]),
    ):
        if not any(
            match["start"] < prior["end"] and prior["start"] < match["end"]
            for prior in accepted
        ):
            accepted.append(match)
    return sorted(accepted, key=lambda match: match["start"])


def redact(text: str, matches: list[dict], mode: str = "labels") -> str:
    if mode not in {"labels", "blocks"}:
        raise InputError("Choose labels or blocks for replacement text.")
    counts, mapping = Counter(), {}
    parts, position = [], 0
    for match in matches:
        key = (match["kind"], match["value"].casefold())
        if key not in mapping:
            counts[match["kind"]] += 1
            mapping[key] = f"[{match['kind'].upper()}_{counts[match['kind']]}]"
        replacement = mapping[key] if mode == "labels" else "[REDACTED]"
        parts.extend([text[position : match["start"]], replacement])
        position = match["end"]
    parts.append(text[position:])
    return "".join(parts)


def public_matches(matches: list[dict]) -> list[dict]:
    # Reports contain categories and positions, not recovered private values.
    return [
        {
            "kind": m["kind"],
            "label": KINDS[m["kind"]],
            "start": m["start"],
            "end": m["end"],
            "length": m["end"] - m["start"],
            "preview": "[private value]",
        }
        for m in matches
    ]
