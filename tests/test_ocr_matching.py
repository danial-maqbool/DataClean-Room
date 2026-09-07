"""Recorded OCR errors, negative controls, and bounded matching regressions."""

import itertools
import json
from unittest import TestCase
from unittest.mock import patch

from app.ocr_matching import (
    Budget,
    distance,
    document_matches,
    require_review,
    review_warnings,
)
from app.detectors import detect
from localdesk.safety import InputError


def layout(lines, *, ocr=True, confidence=92, page=1):
    text, words = "", []
    for row, values in enumerate(lines):
        x = 10
        for value in values:
            start = len(text)
            text += value
            word = {
                "text": value,
                "start": start,
                "end": len(text),
                "bbox": [x, row * 30 + 10, x + len(value) * 8, row * 30 + 30],
                "line": row,
            }
            if ocr:
                word["confidence"] = confidence
            words.append(word)
            x += len(value) * 8 + 10
            text += " "
        text += "\n"
    return {
        "text": text,
        "pages": [{"page": page, "width": 900, "height": 200, "words": words}],
        "warnings": [],
    }


class OCRMatchingTests(TestCase):
    def candidates(self, value, rule="QA_SECRET_CANARY", **kwargs):
        return document_matches(
            layout([[value]], **kwargs), enabled=["custom"], literals=[rule]
        )

    def test_recorded_substitution_is_a_candidate(self):
        matches, review = self.candidates("OA_SECRET_CANARY")
        self.assertEqual(len(matches), 1)
        self.assertEqual(review["candidates"][0]["edits"], 1)
        self.assertFalse(review["requires_confirmation"])
        self.assertTrue(review["candidates"][0]["review_required"])

    def test_insertion_and_deletion(self):
        for value in ["QXA_SECRET_CANARY", "QA_SECRET_CANRY"]:
            with self.subTest(value=value):
                matches, review = self.candidates(value)
                self.assertEqual(len(matches), 1)
                self.assertEqual(review["candidates"][0]["edits"], 1)

    def test_two_edits_in_a_long_value(self):
        matches, review = self.candidates(
            "PROJXCT_PRIVATE_CANARX", "PROJECT_PRIVATE_CANARY"
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(review["candidates"][0]["edits"], 2)

    def test_over_threshold_does_not_invent_a_match(self):
        matches, review = self.candidates("ZZ_ZECRET_CANARY")
        self.assertEqual(matches, [])
        self.assertTrue(review["requires_confirmation"])

    def test_split_words_and_separators_keep_original_spans(self):
        doc = layout([["QA", "SECRET", "CANARY"]])
        matches, review = document_matches(doc, literals=["QA_SECRET_CANARY"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["value"], "QA SECRET CANARY")
        self.assertEqual(review["candidates"][0]["method"], "normalized")

    def test_unicode_normalization_does_not_change_source_offsets(self):
        value = "ＰＲＩＶＡＴＥＶＡＬＵＥ"
        matches, review = self.candidates(value, "PRIVATEVALUE")
        self.assertEqual(matches[0]["end"], len(value))
        self.assertEqual(review["candidates"][0]["method"], "normalized")

    def test_exact_literal_does_not_add_duplicate_fuzzy_candidate(self):
        matches, review = self.candidates("QA_SECRET_CANARY")
        self.assertEqual(len(matches), 1)
        self.assertFalse(review["candidates"])

    def test_exact_overlap_does_not_drop_uncovered_words(self):
        doc = layout([["PRIVATEVALUE", "L0NGSECRET"]])
        matches, review = document_matches(
            doc, literals=["PRIVATEVALUE", "PRIVATEVALUE LONGSECRET"]
        )
        second = doc["pages"][0]["words"][1]
        self.assertTrue(
            any(
                m["start"] < second["end"] and second["start"] < m["end"]
                for m in matches
            )
        )
        self.assertEqual(len(review["candidates"]), 1)

    def test_does_not_fuzzy_match_inside_longer_identifier(self):
        matches, review = self.candidates("UNRELATED_OA_SECRET_CANARY_SUFFIX")
        self.assertEqual(matches, [])
        self.assertTrue(review["requires_confirmation"])

    def test_unrelated_and_short_values_are_negative_controls(self):
        for value, rule in [
            ("PUBLIC_TOTAL_4200", "QA_SECRET_CANARY"),
            ("Alive", "Alice"),
            ("ABAAAAAA", "AAAAAAAA"),
        ]:
            with self.subTest(value=value):
                matches, review = self.candidates(value, rule)
                self.assertEqual(matches, [])
                self.assertTrue(review["requires_confirmation"])

    def test_native_text_is_never_fuzzy_matched(self):
        matches, _ = self.candidates("OA_SECRET_CANARY", ocr=False)
        self.assertEqual(matches, [])
        self.assertEqual(detect("OA_SECRET_CANARY", literals=["QA_SECRET_CANARY"]), [])

    def test_disabled_custom_rule_stays_disabled(self):
        matches, review = document_matches(
            layout([["OA_SECRET_CANARY"]]), enabled=[], literals=["QA_SECRET_CANARY"]
        )
        self.assertEqual(matches, [])
        self.assertFalse(review["requires_confirmation"])

    def test_low_confidence_does_not_discard_private_region(self):
        matches, review = self.candidates("OA_SECRET_CANARY", confidence=15)
        self.assertEqual(len(matches), 1)
        self.assertIn("low", " ".join(review_warnings(review)))

    def test_nonfinite_confidence_is_not_a_probability(self):
        for score in [float("nan"), float("inf"), None, -1, True]:
            matches, review = self.candidates("OA_SECRET_CANARY", confidence=score)
            self.assertEqual(len(matches), 1)
            self.assertIsNone(review["candidates"][0]["ocr_confidence"])
            json.dumps(review, allow_nan=False)

    def test_no_candidate_crosses_a_line_or_column(self):
        for doc in [
            layout([["QA_SECRET"], ["CANARY"]]),
            layout([["QA_SECRET", "CANARY"]]),
        ]:
            if (
                len(doc["pages"][0]["words"]) == 2
                and doc["pages"][0]["words"][1]["line"] == 0
            ):
                doc["pages"][0]["words"][1]["bbox"] = [700, 10, 780, 30]
            matches, _ = document_matches(doc, literals=["QA_SECRET_CANARY"])
            self.assertEqual(matches, [])

    def test_native_words_separate_ocr_runs(self):
        doc = layout([["QA_SECRET", "CANARY"]])
        doc["pages"][0]["words"][1].pop("confidence")
        matches, _ = document_matches(doc, literals=["QA_SECRET_CANARY"])
        self.assertEqual(matches, [])

    def test_pages_do_not_join(self):
        doc = layout([["QA_SECRET"]])
        other = layout([["CANARY"]], page=2)
        shift = len(doc["text"])
        for word in other["pages"][0]["words"]:
            word["start"] += shift
            word["end"] += shift
        doc["text"] += other["text"]
        doc["pages"] += other["pages"]
        self.assertEqual(document_matches(doc, literals=["QA_SECRET_CANARY"])[0], [])

    def test_review_metadata_has_no_private_value(self):
        _, review = self.candidates("OA_SECRET_CANARY")
        encoded = json.dumps(review)
        self.assertNotIn("OA_SECRET_CANARY", encoded)
        self.assertNotIn("QA_SECRET_CANARY", encoded)
        self.assertFalse(review["scores_are_probabilities"])

    def test_missing_rule_requires_explicit_boolean_confirmation(self):
        _, review = self.candidates("Public")
        for flag in [False, "true", 1, None]:
            with self.subTest(flag=flag), self.assertRaises(InputError):
                require_review(review, flag)
        require_review(review, True)

    def test_invalid_ocr_geometry_and_offsets_fail_closed(self):
        for box in [
            [0, 0, 0, 0],
            [-1, 0, 40, 40],
            [0, 0, 10000, 40],
            [0, 0, float("nan"), 40],
        ]:
            doc = layout([["OA_SECRET_CANARY"]])
            doc["pages"][0]["words"][0]["bbox"] = box
            with self.assertRaisesRegex(InputError, "coordinates"):
                document_matches(doc, literals=["QA_SECRET_CANARY"])
        doc = layout([["OA_SECRET_CANARY"]])
        doc["pages"][0]["words"][0]["end"] = 9999
        with self.assertRaisesRegex(InputError, "positions"):
            document_matches(doc, literals=["QA_SECRET_CANARY"])

    def test_work_limits_fail_closed(self):
        with (
            patch("app.ocr_matching.MAX_COMPARISONS", 0),
            self.assertRaisesRegex(InputError, "comparison limit"),
        ):
            self.candidates("OA_SECRET_CANARY")
        with (
            patch("app.ocr_matching.MAX_DISTANCE_CELLS", 0),
            self.assertRaisesRegex(InputError, "distance limit"),
        ):
            distance("abcdefgh", "abxdexgh", 2, Budget())

    def test_invalid_rules_use_existing_validation(self):
        for rules in ["secret", [None], ["a" * 201]]:
            with self.subTest(rules=rules), self.assertRaises(InputError):
                document_matches(layout([["hello"]]), literals=rules)

    def test_banded_distance_matches_reference(self):
        def reference(a, b):
            row = list(range(len(b) + 1))
            for i, ca in enumerate(a, 1):
                nxt = [i]
                for j, cb in enumerate(b, 1):
                    nxt.append(min(row[j] + 1, nxt[-1] + 1, row[j - 1] + (ca != cb)))
                row = nxt
            return row[-1]

        values = [
            "".join(xs) for n in range(5) for xs in itertools.product("ab", repeat=n)
        ]
        for a in values:
            for b in values:
                for limit in (1, 2):
                    self.assertEqual(
                        distance(a, b, limit, Budget()),
                        min(limit + 1, reference(a, b)),
                        (a, b, limit),
                    )
