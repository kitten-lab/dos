"""Creator-tool shorthand: /c → create, /s → spawn."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from wbs_seed_fixtures import seed_world_story
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class CreatorShorthandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_slash_c_create(self) -> None:
        r = dispatch(self.world, "/c material Test Filament | Thin test.")
        self.assertTrue(r.ok, r.message)
        msg = plain(r.message)
        self.assertIn("Test Filament", msg)

    def test_slash_s_spawn(self) -> None:
        self.assertTrue(dispatch(self.world, "create object Shorthand Box").ok)
        r = dispatch(self.world, "/s shorthand-box as Pocket Box")
        self.assertTrue(r.ok, r.message)
        msg = plain(r.message)
        self.assertIn("Pocket Box", msg)

    def test_slash_c_usage_when_bare(self) -> None:
        r = dispatch(self.world, "/c")
        self.assertTrue(r.ok)
        msg = plain(r.message)
        self.assertTrue(
            "Usage: create" in msg or "create --type" in msg or "Usage (flags" in msg,
            msg=msg,
        )

    def test_help_slash_c(self) -> None:
        r = dispatch(self.world, "help /c")
        self.assertTrue(r.ok)
        self.assertIn("create", plain(r.message).lower())

    def test_old_dot_no_longer_shorthand(self) -> None:
        r = dispatch(self.world, ".c material Ghost | no.")
        self.assertFalse(r.ok)
        self.assertIn("unknown", plain(r.message).lower())


if __name__ == "__main__":
    unittest.main()
