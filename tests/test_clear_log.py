"""clear/clr and clear-on-go for session transcript."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from dos import cli
from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.help_topics import resolve_topic
from wbs_seed_fixtures import seed_world_classic as seed_world
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world(conn)
    return World(conn)


class ClearCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_clear_and_clr_set_flag(self) -> None:
        for cmd in ("clear", "clr"):
            r = dispatch(self.world, cmd)
            self.assertTrue(r.ok, msg=r.message)
            self.assertTrue(r.clear_log, msg=cmd)
            # Totally blank — no “log cleared” / tips text
            self.assertEqual(plain(r.message).strip(), "")

    def test_go_success_clears_log(self) -> None:
        r = dispatch(self.world, "go through the mirror")
        self.assertTrue(r.ok, msg=r.message)
        self.assertTrue(r.clear_log)
        text = plain(r.message)
        self.assertIn("Hall of Shelved Years", text)
        self.assertIn("→", text)

    def test_go_failure_does_not_clear(self) -> None:
        r = dispatch(self.world, "go nowhere-real-xyz")
        self.assertTrue(r.ok)
        self.assertFalse(r.clear_log)
        self.assertIn("No path", plain(r.message))

    def test_go_missing_arg_does_not_clear(self) -> None:
        r = dispatch(self.world, "go")
        self.assertFalse(r.clear_log)

    def test_look_does_not_clear(self) -> None:
        r = dispatch(self.world, "look")
        self.assertTrue(r.ok)
        self.assertFalse(r.clear_log)

    def test_cls_clears_and_looks(self) -> None:
        for cmd in ("cls", "refresh", "ref", "blink"):
            r = dispatch(self.world, cmd)
            self.assertTrue(r.ok, msg=cmd)
            self.assertTrue(r.clear_log, msg=cmd)
            text = plain(r.message)
            self.assertIn("Location:", text, msg=cmd)

    def test_help_clear_resolves(self) -> None:
        self.assertEqual(resolve_topic("clear"), "clear")
        self.assertEqual(resolve_topic("clr"), "clear")
        self.assertEqual(resolve_topic("cls"), "cls")
        self.assertEqual(resolve_topic("blink"), "cls")
        r = dispatch(self.world, "help clear")
        self.assertTrue(r.ok)
        text = plain(r.message).lower()
        self.assertIn("clear", text)
        self.assertIn("go", text)


class ClearCliWiringTests(unittest.TestCase):
    def test_tui_and_repl_honor_clear_log(self) -> None:
        src = inspect.getsource(cli)
        self.assertIn("clear_log", src)
        self.assertIn("_clear_world_log", src)
        self.assertIn("log.clear()", src)
        self.assertIn("_clear_repl_screen", src)
        # Boot banner exists for first load; clr path must not re-inject tips
        self.assertIn("_studio_boot_banner_markup", src)
        self.assertIn("_studio_boot_panel", src)
        clear_src = inspect.getsource(cli.run_textual)
        # _clear_world_log is nested; ensure blank clear (no banner write after clear)
        self.assertIn("def _clear_world_log", clear_src)
        self.assertIn("log.clear()", clear_src)
        # Pure clear skips command echo
        self.assertIn('clear_log and not (message or "").strip()', clear_src)


if __name__ == "__main__":
    unittest.main()
