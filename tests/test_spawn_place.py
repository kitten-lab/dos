"""Place primes as room templates: spawn free-standing, not nested here."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.seed import seed_world_void
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_void(conn)
    return World(conn)


class SpawnPlaceTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        self.assertTrue(
            dispatch(self.world, "create place Room | Generic chamber.").ok
        )

    def test_spawn_place_not_nested_in_current(self) -> None:
        r = dispatch(self.world, "spawn room as Kitchen")
        self.assertTrue(r.ok, r.message)
        self.assertIn("Spawned place", plain(r.message))
        self.assertIn("unlinked", plain(r.message).lower())
        kitchen = self.world.find_instances_by_name("Kitchen", kind="place")
        self.assertEqual(len(kitchen), 1)
        # Free-standing: not contained in the Void / current place
        self.assertIsNone(self.world.container_of(kitchen[0].id))
        look = plain(dispatch(self.world, "look").message)
        self.assertNotIn("Kitchen", look)

    def test_spawn_place_link_and_go(self) -> None:
        self.assertTrue(dispatch(self.world, "spawn room as Kitchen").ok)
        self.assertTrue(
            dispatch(self.world, "link kitchen-door -> Kitchen both").ok
        )
        r = dispatch(self.world, "go kitchen-door")
        self.assertTrue(r.ok, r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(loc.name, "Kitchen")
        # Same prime as Room
        ven = self.world.find_ven("Room")
        assert ven is not None
        self.assertEqual(loc.ven_id, ven.id)

    def test_multiple_rooms_share_prime(self) -> None:
        self.assertTrue(dispatch(self.world, "spawn room as Kitchen").ok)
        self.assertTrue(dispatch(self.world, "spawn room as Bedroom").ok)
        ven = self.world.find_ven("Room")
        assert ven is not None
        insts = self.world.list_instances_of_ven(ven.id)
        self.assertEqual(len(insts), 2)
        names = {i.name for i in insts}
        self.assertEqual(names, {"Kitchen", "Bedroom"})
        listed = plain(dispatch(self.world, "instances room").message)
        self.assertIn("Kitchen", listed)
        self.assertIn("Bedroom", listed)

    def test_object_spawn_still_lands_here(self) -> None:
        self.assertTrue(dispatch(self.world, "create object Chair").ok)
        self.assertTrue(dispatch(self.world, "spawn chair").ok)
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Chair", look)


if __name__ == "__main__":
    unittest.main()
