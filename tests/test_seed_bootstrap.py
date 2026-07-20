"""Bootstrap seed: Herenow + Builder (person/archetype); Base / Start / Place only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect, get_meta
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world_bootstrap
from digital_office_spaces.world import World


class BootstrapSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        self.conn = connect(Path(tmp.name))
        seed_world_bootstrap(self.conn)
        self.world = World(self.conn)

    def test_meta_and_place(self) -> None:
        self.assertEqual(get_meta(self.conn, "world_name"), "Bootstrap")
        self.assertEqual(get_meta(self.conn, "seed_version"), "bootstrap-3")
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(loc.name, "Herenow")
        self.assertEqual(loc.ven_name, "Place")
        self.assertEqual(len(self.world.exits(loc.id)), 0)

    def test_no_note_or_floor_props(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        pid = self.world.player_id()
        others = [c for c in self.world.contents(loc.id) if c.id != pid]
        self.assertEqual(others, [])
        self.assertIsNone(self.world.find_ven("Note"))
        self.assertIsNone(self.world.find_ven("Small Note"))
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Herenow", look)
        self.assertNotIn("Small Note", look)
        self.assertNotIn("note", look.lower())

    def test_builder_is_person_archetype(self) -> None:
        builder_ven = self.world.find_ven("Builder")
        assert builder_ven is not None
        self.assertEqual(builder_ven.kind, "person")
        self.assertEqual((builder_ven.subtype or "").lower(), "archetype")
        pid = self.world.player_id()
        assert pid is not None
        player = self.world.get_instance(pid)
        assert player is not None
        self.assertEqual(player.ven_id, builder_ven.id)
        self.assertEqual((player.ven_subtype or "").lower(), "archetype")

    def test_primes_only(self) -> None:
        names = {v.name for v in self.world.list_vens()}
        self.assertEqual(names, {"Base", "Start", "Place", "Builder"})


if __name__ == "__main__":
    unittest.main()
