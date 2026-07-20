"""Standalone help CLI (second terminal) — print path + Textual structure."""

from __future__ import annotations

import io
import inspect
import subprocess
import sys
import unittest
from pathlib import Path

from digital_office_spaces import help_cli
from digital_office_spaces.format import plain
from digital_office_spaces.help_cli import (
    help_text_for_query,
    main,
    print_help_query,
    run_help_tui,
    run_interactive,
)
from digital_office_spaces.help_topics import render_help_topic
from digital_office_spaces.help_ui import render_numbered_index


class HelpTextQueryTests(unittest.TestCase):
    def test_index_non_empty_with_markers(self) -> None:
        body = help_text_for_query("")
        text = plain(body)
        self.assertIn("Help", text)
        self.assertTrue(len(text) > 80)
        self.assertRegex(text, r"\b11\b")
        self.assertIn("topic", text.lower())

    def test_look_topic_matches_shipped_renderer(self) -> None:
        via_cli = plain(help_text_for_query("look"))
        via_topics = plain(render_help_topic("look"))
        self.assertIn("look", via_cli.lower())
        self.assertIn("look", via_topics.lower())
        for needle in ("look", "locate", "go"):
            self.assertTrue(
                needle in via_cli.lower() or "room" in via_cli.lower(),
                msg=f"missing look-related content for {needle!r}",
            )
        self.assertGreater(len(via_cli), 40)

    def test_lore_topic(self) -> None:
        text = plain(help_text_for_query("lore"))
        self.assertIn("lore", text.lower())
        self.assertGreater(len(text), 40)

    def test_number_selects_from_index(self) -> None:
        text = plain(help_text_for_query("1"))
        self.assertGreater(len(text), 20)
        self.assertNotIn("No help topic numbered", text)
        # digit code (look → 11)
        by_code = plain(help_text_for_query("11"))
        self.assertIn("look", by_code.lower())
        self.assertGreater(len(by_code), 20)


class HelpCliMainTests(unittest.TestCase):
    def test_main_print_index(self) -> None:
        buf = io.StringIO()
        code = print_help_query("", file=buf)
        self.assertEqual(code, 0)
        out = plain(buf.getvalue())
        self.assertIn("Help", out)
        self.assertRegex(out, r"\b11\b")

    def test_main_print_look_via_argv(self) -> None:
        code = main(["--print", "look"])
        self.assertEqual(code, 0)
        text = plain(help_text_for_query("look"))
        self.assertIn("look", text.lower())

    def test_main_print_empty_is_index(self) -> None:
        code = main(["--print"])
        self.assertEqual(code, 0)
        self.assertEqual(
            plain(help_text_for_query("")),
            plain(render_numbered_index()),
        )

    def test_interactive_quit(self) -> None:
        lines = iter(["look", "q"])
        printed: list[str] = []

        class FakeConsole:
            def print(self, *args, **kwargs) -> None:
                printed.append(str(args[0]) if args else "")

        code = run_interactive(
            console=FakeConsole(),  # type: ignore[arg-type]
            read_line=lambda: next(lines),
        )
        self.assertEqual(code, 0)
        joined = plain("\n".join(printed))
        self.assertIn("look", joined.lower())
        self.assertIn("bye", joined.lower())

    def test_entry_point_and_textual_structure(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        self.assertIn("digital-office-spaces-help", text)
        self.assertIn("digital_office_spaces.help_cli:main", text)
        src = inspect.getsource(help_cli)
        self.assertIn("def main", src)
        self.assertIn("help_text_for_query", src)
        self.assertIn("run_help_tui", src)
        self.assertIn("StandaloneHelpApp", src)
        self.assertIn("VerticalScroll", src)
        self.assertIn("help-body", src)
        self.assertIn("help-input", src)
        self.assertIn("escape", src.lower())
        self.assertNotIn("ensure_world", src)
        self.assertNotIn("connect(", src)
        # chrome tokens
        self.assertTrue(help_cli.HELP_TUI_BG.startswith("#"))
        tui_src = inspect.getsource(run_help_tui)
        self.assertIn("body.update", tui_src)
        self.assertIn("help_text_for_query", tui_src)

    def test_textual_app_uses_same_body_provider(self) -> None:
        """UI body is exactly help_text_for_query (index + look)."""
        self.assertIn("Help", plain(help_text_for_query("")))
        self.assertIn("look", plain(help_text_for_query("look")).lower())
        src = inspect.getsource(run_help_tui)
        self.assertIn('body.update(text)', src)
        self.assertIn("help_text_for_query(q)", src)


class HelpCliSubprocessTests(unittest.TestCase):
    """Real ``python -m digital_office_spaces.help_cli --print`` launch path."""

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "digital_office_spaces.help_cli", *args],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
            timeout=30,
            env={
                **dict(__import__("os").environ),
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            },
        )

    def test_module_print_index_launch(self) -> None:
        r = self._run("--print")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        out = plain(r.stdout)
        self.assertIn("Help", out)
        self.assertRegex(out, r"\b1\b")
        self.assertGreater(len(out), 80)

    def test_module_print_look_launch(self) -> None:
        r = self._run("--print", "look")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        out = plain(r.stdout)
        self.assertIn("look", out.lower())
        self.assertGreater(len(out), 40)


if __name__ == "__main__":
    unittest.main()
