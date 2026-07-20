"""Put people/objects into adjacent rooms via exits (no inventory hop)."""

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


class PutAdjacentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        self.assertTrue(dispatch(self.world, "dig Side Alcove").ok)
        self.assertTrue(
            dispatch(self.world, "link alcove-in -> Side Alcove both").ok
        )

    def test_put_object_via_exit_label(self) -> None:
        self.assertTrue(dispatch(self.world, "create object Test Stone").ok)
        self.assertTrue(dispatch(self.world, "spawn test-stone").ok)
        r = dispatch(self.world, "put test-stone in alcove-in")
        self.assertTrue(r.ok, r.message)
        self.assertIn("Moved", plain(r.message))
        # Not here anymore
        here = plain(dispatch(self.world, "look").message)
        self.assertNotIn("Test Stone", here)
        # In adjacent place
        dests = self.world.find_instances_by_name("Side Alcove", kind="place")
        self.assertEqual(len(dests), 1)
        names = [c.name for c in self.world.contents(dests[0].id)]
        self.assertTrue(any("Stone" in n for n in names), names)

    def test_put_person_via_place_name(self) -> None:
        self.assertTrue(dispatch(self.world, "create person Scout").ok)
        self.assertTrue(dispatch(self.world, "spawn scout").ok)
        r = dispatch(self.world, "put scout into Side Alcove")
        self.assertTrue(r.ok, r.message)
        self.assertIn("Moved", plain(r.message))
        dests = self.world.find_instances_by_name("Side Alcove", kind="place")
        self.assertEqual(len(dests), 1)
        names = [c.name for c in self.world.contents(dests[0].id)]
        self.assertTrue(any("Scout" in n for n in names), names)

    def test_put_from_inv_to_adjacent_and_undo(self) -> None:
        self.assertTrue(dispatch(self.world, "create object Pocket Coin").ok)
        self.assertTrue(dispatch(self.world, "spawn pocket-coin").ok)
        self.assertTrue(dispatch(self.world, "take pocket-coin").ok)
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Coin", inv)
        r = dispatch(self.world, "put coin in Side Alcove")
        self.assertTrue(r.ok, r.message)
        inv2 = plain(dispatch(self.world, "inv").message)
        self.assertNotIn("Coin", inv2)
        self.assertTrue(dispatch(self.world, "undo").ok)
        inv3 = plain(dispatch(self.world, "inv").message)
        self.assertIn("Coin", inv3)

    def test_put_in_here_from_inv(self) -> None:
        self.assertTrue(dispatch(self.world, "create object Floor Marble").ok)
        self.assertTrue(dispatch(self.world, "spawn floor-marble").ok)
        self.assertTrue(dispatch(self.world, "take floor-marble").ok)
        r = dispatch(self.world, "put marble in here")
        self.assertTrue(r.ok, r.message)
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Marble", look)

    def test_box_put_still_works(self) -> None:
        self.assertTrue(dispatch(self.world, "create object Tiny Box").ok)
        self.assertTrue(dispatch(self.world, "spawn tiny-box").ok)
        self.assertTrue(dispatch(self.world, "create object Bean").ok)
        self.assertTrue(dispatch(self.world, "spawn bean").ok)
        r = dispatch(self.world, "put bean in box")
        self.assertTrue(r.ok, r.message)
        self.assertIn("Put", plain(r.message))


if __name__ == "__main__":
    unittest.main()
