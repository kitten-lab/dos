"""Canonical content measure (72) and ruler."""

from __future__ import annotations

import unittest

from dos.book import PAGE_VIEW_WIDTH
from dos.format import TURN_RULE_WIDTH, plain, turn_separator
from dos.measure import CONTENT_MEASURE, measure_ruler, turn_rule_ascii


class ContentMeasureTests(unittest.TestCase):
    def test_shared_artboard(self) -> None:
        self.assertEqual(CONTENT_MEASURE, 72)
        self.assertEqual(TURN_RULE_WIDTH, CONTENT_MEASURE)
        self.assertEqual(PAGE_VIEW_WIDTH, CONTENT_MEASURE)

    def test_ruler_length_and_markers(self) -> None:
        r = measure_ruler(72)
        self.assertEqual(len(r), 72)
        self.assertEqual(r[9], "1")   # column 10
        self.assertEqual(r[19], "2")  # column 20
        self.assertEqual(r[4], "+")   # column 5

    def test_turn_sep_ascii_measure(self) -> None:
        self.assertEqual(turn_rule_ascii(72), "-" * 72)
        self.assertEqual(plain(turn_separator()), "-" * 72)


if __name__ == "__main__":
    unittest.main()
