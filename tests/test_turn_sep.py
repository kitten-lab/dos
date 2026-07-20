"""Compact turn separator for the main log / REPL."""

from __future__ import annotations

import inspect
import unittest

from digital_office_spaces import cli
from digital_office_spaces import format as fmt
from digital_office_spaces.format import TURN_RULE_WIDTH, plain, turn_separator


class TurnSeparatorTests(unittest.TestCase):
    def test_dense_rule_not_mid_dots(self) -> None:
        raw = turn_separator()
        # Shipped helper: dim ASCII rule at content measure, not spaced mid-dots
        self.assertIn("-", raw)
        self.assertIn("[dim]", raw)
        self.assertNotIn("─", raw)
        self.assertNotIn("· · ·", raw)
        self.assertNotIn("· ·", raw)
        # Single logical line of rules
        self.assertEqual(raw.count("\n"), 0)
        plain_sep = plain(raw)
        self.assertEqual(plain_sep, "-" * TURN_RULE_WIDTH)
        self.assertEqual(len(plain_sep), 72)
        # No multi-line blank padding inside the helper itself
        self.assertFalse(raw.startswith("\n"))
        self.assertFalse(raw.endswith("\n"))

    def test_cli_call_sites_use_helper_without_triple_blank_padding(self) -> None:
        src = inspect.getsource(cli)
        self.assertIn("turn_separator", src)
        # Old sparse padding pattern must be gone
        self.assertNotIn('"\\n" + fmt.turn_separator() + "\\n"', src)
        self.assertNotIn("'\\n' + fmt.turn_separator() + '\\n'", src)
        # REPL must not wrap message with blank prints on both sides + sep
        repl = inspect.getsource(cli.run_repl)
        # After message: print separator once (no console.print() sandwich required)
        self.assertIn("turn_separator()", repl)
        # Old blank-line sandwich around the result message is gone
        self.assertNotIn(
            "console.print()\n            console.print(result.message)\n            console.print()",
            repl,
        )

        # TUI turn writer
        tui = inspect.getsource(cli.run_textual)
        self.assertIn("turn_separator()", tui)
        self.assertNotIn('"\\n" + fmt.turn_separator()', tui)
        self.assertNotIn("'\\n' + fmt.turn_separator()", tui)
        self.assertNotIn("\\n\" + fmt.turn_separator() + \"\\n\"", tui)
        # Editor cancel/save both finish as a full turn (HR + command + result)
        self.assertIn("_on_editor_done", tui)
        self.assertIn('fmt.hint("Editor cancelled.")', tui)
        # Cancel must go through _write_world_turn (not a bare log.write of the hint)
        # Find the cancel branch: _write_world_turn near Editor cancelled
        self.assertIn("_write_world_turn", tui)
        # No pre-turn command echo while the modal is opening
        self.assertNotIn("Opening editor ·", tui)


if __name__ == "__main__":
    unittest.main()
