"""Cohesive help pane: digit-fast nav, cheat sheet default."""

from __future__ import annotations

import inspect
import re
import unittest

from digital_office_spaces import cli
from digital_office_spaces.format import plain
from digital_office_spaces.help_topics import topic_index_terms
from digital_office_spaces.help_ui import (
    HelpPane,
    numbered_index_entries,
    parse_help_command,
    render_cheat_sheet,
    render_numbered_index,
    render_section,
    topic_key_for_index_term,
)


class NumberedIndexTests(unittest.TestCase):
    def test_entries_use_digit_codes(self) -> None:
        entries = numbered_index_entries()
        self.assertGreaterEqual(len(entries), 5)
        codes = [e[0] for e in entries]
        self.assertEqual(codes[0], "11")  # look
        self.assertTrue(
            all(isinstance(c, str) and re.match(r"^\d{2}$", c) for c in codes)
        )
        self.assertEqual(len(codes), len(set(codes)))
        terms = {t for t, _ in topic_index_terms()}
        for _code, label, _sum, key in entries:
            self.assertTrue(label)
            self.assertTrue(key)
            self.assertTrue(
                any(topic_key_for_index_term(t) == key for t in terms),
                msg=f"orphan key {key}",
            )
        look = next(e for e in entries if e[3] == "look")
        self.assertEqual(look[0], "11")

    def test_cheat_sheet_is_compact(self) -> None:
        text = plain(render_cheat_sheet())
        self.assertIn("cheat sheet", text.lower())
        self.assertIn("MOVEMENT", text)
        self.assertIn("ENV CONTROLS", text)
        self.assertIn("look", text.lower())
        self.assertRegex(text, r"(?m)^\s*11\s+look")
        self.assertRegex(text, r"(?m)^1\s+MOVEMENT")
        self.assertIn("─", text)
        self.assertIn("section", text.lower())
        self.assertIn("close pane", text.lower())
        self.assertIn("root cheat sheet", text.lower())
        self.assertNotIn("Describe the place you are in", text)

    def test_section_expands_codes(self) -> None:
        body = render_section(1)
        assert body is not None
        text = plain(body)
        self.assertIn("11", text)
        self.assertIn("look", text.lower())
        self.assertIn("Describe", text)

    def test_full_catalog_still_available(self) -> None:
        text = plain(render_numbered_index())
        self.assertIn("11", text)
        self.assertIn("full catalog", text.lower())
        self.assertIn("MOVEMENT", text)


class HelpPaneNavTests(unittest.TestCase):
    def test_toggle_opens_cheat_sheet(self) -> None:
        pane = HelpPane()
        r = pane.handle_line("help")
        self.assertTrue(r.handled)
        self.assertTrue(pane.open)
        self.assertEqual(pane.mode, "cheat")
        body = plain(pane.body())
        self.assertIn("cheat sheet", body.lower())
        self.assertIn("look", body.lower())
        r2 = pane.handle_line("?")
        self.assertTrue(r2.handled)
        self.assertFalse(pane.open)

    def test_digit_topic_and_section_nav(self) -> None:
        pane = HelpPane()
        pane.handle_line("help")
        # 11 = look (section 1 item 1) — numpad jump
        r = pane.handle_line("11")
        self.assertTrue(r.refresh_help)
        self.assertEqual(pane.mode, "topic")
        self.assertEqual(pane.topic_key, "look")
        # 0 = root
        pane.handle_line("0")
        self.assertEqual(pane.mode, "cheat")
        # 1 = section
        pane.handle_line("1")
        self.assertEqual(pane.mode, "section")
        self.assertEqual(pane.section_n, 1)
        # In section, single digit 2 = second item (go)
        pane.handle_line("2")
        self.assertEqual(pane.mode, "topic")
        self.assertEqual(pane.topic_key, "go")
        # 0 roots again
        pane.handle_line("0")
        self.assertEqual(pane.mode, "cheat")

    def test_legacy_letter_code_still_works(self) -> None:
        pane = HelpPane()
        pane.handle_line("help")
        pane.handle_line("1a")
        self.assertEqual(pane.mode, "topic")
        self.assertEqual(pane.topic_key, "look")

    def test_help_all_catalog(self) -> None:
        pane = HelpPane()
        pane.handle_line("help all")
        self.assertTrue(pane.open)
        self.assertEqual(pane.mode, "catalog")
        self.assertIn("11", plain(pane.body()))

    def test_help_topic_direct(self) -> None:
        pane = HelpPane()
        r = pane.handle_line("help look")
        self.assertTrue(r.handled)
        self.assertEqual(pane.mode, "topic")
        self.assertEqual(pane.topic_key, "look")


class ParseHelpTests(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(parse_help_command("help"), "")
        self.assertEqual(parse_help_command("?"), "")
        self.assertEqual(parse_help_command("help look"), "look")
        self.assertIsNone(parse_help_command("look"))


class TuiStructureTests(unittest.TestCase):
    def test_single_help_pane_no_modal_dual_system(self) -> None:
        src = inspect.getsource(cli.run_textual)
        self.assertIn("HelpPane", src)
        self.assertIn("help-pane", src)
        self.assertIn("handle_line", src)
        self.assertNotIn("HelpDialog", src)
        self.assertIn("make_book_reader_screen", src)

    def test_help_route_not_writing_index_to_log_path(self) -> None:
        src = inspect.getsource(cli.run_textual)
        self.assertIn("route.handled", src)
        self.assertIn("_refresh_help_pane", src)
        self.assertIn("_write_world_turn", src)

    def test_help_pane_wider_and_sharp_dark_chrome(self) -> None:
        self.assertGreaterEqual(cli.TUI_HELP_PANE_WIDTH, 52)
        src = inspect.getsource(cli.run_textual)
        self.assertIn("border: solid", src)
        self.assertIn("{TUI_HELP_PANE_WIDTH}", src)
        self.assertNotIn("{TUI_BOOK_PANE_WIDTH}", src)
        self.assertFalse(hasattr(cli, "TUI_BOOK_PANE_WIDTH"))
        self.assertIn("make_book_reader_screen", src)


if __name__ == "__main__":
    unittest.main()
