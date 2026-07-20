"""Empty suite seed: unfurnished office shell on the wire."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect, get_meta
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world, seed_world_empty
from digital_office_spaces.world import World


def _empty_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_empty(conn)
    return World(conn)


class EmptySeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _empty_world()

    def test_seed_world_flavor_empty(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world(conn, flavor="empty")
        w = World(conn)
        loc = w.player_location()
        assert loc is not None
        self.assertIn("EMPTY", loc.name.upper())
        self.assertEqual(get_meta(conn, "seed_version"), "empty-1")

    def test_void_alias_is_empty(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world(conn, flavor="void")
        loc = World(conn).player_location()
        assert loc is not None
        self.assertIn("EMPTY", loc.name.upper())

    def test_start_no_exits_has_whiteboard(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(len(self.world.exits(loc.id)), 0)

        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Empty", look)
        self.assertIn("Whiteboard", look)
        self.assertNotIn("Hearth", look)
        self.assertNotIn("Cathedral", look)
        self.assertNotIn("loves you backwards", look.lower())

        exits = plain(dispatch(self.world, "exits").message)
        self.assertIn("No paths", exits)

    def test_who_is_operator(self) -> None:
        who = plain(dispatch(self.world, "who").message)
        self.assertTrue("You" in who or "Operator" in who, msg=who)
        self.assertNotIn("Cartographer", who)


if __name__ == "__main__":
    unittest.main()
