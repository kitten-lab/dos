"""Unlink / delink / rename place exits."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class LinkEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        self.assertTrue(dispatch(self.world, "dig Side Alcove").ok)

    def test_unlink_one_way(self) -> None:
        self.assertTrue(dispatch(self.world, "link alcove-in -> Side Alcove").ok)
        exits = plain(dispatch(self.world, "exits").message)
        self.assertIn("alcove-in", exits.lower())
        r = dispatch(self.world, "unlink alcove-in")
        self.assertTrue(r.ok, r.message)
        self.assertIn("Unlinked", plain(r.message))
        exits2 = plain(dispatch(self.world, "exits").message)
        self.assertNotIn("alcove-in", exits2.lower())

    def test_unlink_both_and_undo(self) -> None:
        self.assertTrue(dispatch(self.world, "link alcove-in -> Side Alcove both").ok)
        loc = self.world.player_location()
        assert loc is not None
        dests = self.world.find_instances_by_name("Side Alcove", kind="place")
        self.assertEqual(len(dests), 1)
        dest = dests[0]
        self.assertIsNotNone(self.world.find_exit(loc.id, "alcove-in"))
        self.assertIsNotNone(self.world.find_exit(dest.id, "alcove-in"))

        r = dispatch(self.world, "delink alcove-in both")
        self.assertTrue(r.ok, r.message)
        self.assertIsNone(self.world.find_exit(loc.id, "alcove-in"))
        self.assertIsNone(self.world.find_exit(dest.id, "alcove-in"))

        self.assertTrue(dispatch(self.world, "undo").ok)
        self.assertIsNotNone(self.world.find_exit(loc.id, "alcove-in"))
        self.assertIsNotNone(self.world.find_exit(dest.id, "alcove-in"))

    def test_link_rename_and_undo(self) -> None:
        # Unique labels — seed hearth already has compass exits like east.
        self.assertTrue(dispatch(self.world, "link alcove-in -> Side Alcove").ok)
        r = dispatch(self.world, "link rename alcove-in as alcove-door")
        self.assertTrue(r.ok, r.message)
        self.assertIn("renamed", plain(r.message).lower())
        loc = self.world.player_location()
        assert loc is not None
        self.assertIsNone(self.world.find_exit(loc.id, "alcove-in"))
        ex = self.world.find_exit(loc.id, "alcove-door")
        self.assertIsNotNone(ex)
        assert ex is not None
        self.assertEqual(ex["label"], "alcove-door")

        self.assertTrue(dispatch(self.world, "undo").ok)
        self.assertIsNotNone(self.world.find_exit(loc.id, "alcove-in"))
        self.assertIsNone(self.world.find_exit(loc.id, "alcove-door"))

    def test_rename_collision(self) -> None:
        self.assertTrue(dispatch(self.world, "dig Other Nook").ok)
        self.assertTrue(dispatch(self.world, "link path-a -> Side Alcove").ok)
        self.assertTrue(dispatch(self.world, "link path-b -> Other Nook").ok)
        r = dispatch(self.world, "link rename path-a as path-b")
        self.assertIn("already", plain(r.message).lower())

    def test_help_unlink(self) -> None:
        r = dispatch(self.world, "help unlink")
        self.assertTrue(r.ok)
        self.assertIn("unlink", plain(r.message).lower())


if __name__ == "__main__":
    unittest.main()
