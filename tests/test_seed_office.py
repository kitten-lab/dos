"""Office seed: company campus on the wire — data, schedules, chats in place."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect, get_meta
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world, seed_world_office
from digital_office_spaces.world import World


def _office_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_office(conn)
    return World(conn)


class OfficeSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _office_world()

    def test_default_seed_world_is_office(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world(conn)
        w = World(conn)
        loc = w.player_location()
        assert loc is not None
        self.assertIn("LOBBY", loc.name.upper())
        self.assertEqual(get_meta(conn, "seed_version"), "office-1")
        self.assertEqual(get_meta(conn, "world_name"), "Digital Office")

    def test_legacy_flavors_map_to_office(self) -> None:
        for flavor in ("story", "classic", "tavern", "wick"):
            tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
            tmp.close()
            conn = connect(Path(tmp.name))
            seed_world(conn, flavor=flavor)
            loc = World(conn).player_location()
            assert loc is not None
            self.assertIn("LOBBY", loc.name.upper(), msg=flavor)

    def test_start_in_lobby_not_fantasy(self) -> None:
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Lobby", look)
        self.assertIn("Handbook", look)
        self.assertNotIn("Hearth", look)
        self.assertNotIn("Cathedral", look)
        self.assertNotIn("Wick", look)
        self.assertNotIn("Void", look)

    def test_campus_paths(self) -> None:
        dispatch(self.world, "go into the open floor")
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Open Floor", look)
        self.assertIn("Channel", look)

        dispatch(self.world, "go north")
        meet = plain(dispatch(self.world, "look").message)
        self.assertIn("Meeting", meet)
        self.assertIn("Calendar", meet)

        dispatch(self.world, "go south")  # back to floor
        dispatch(self.world, "go south")  # records
        rec = plain(dispatch(self.world, "look").message)
        self.assertIn("Records", rec)
        self.assertIn("Cabinet", rec)

    def test_collab_surfaces_openable(self) -> None:
        r = dispatch(self.world, "book open handbook")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Digital Office", text)

        dispatch(self.world, "go into the open floor")
        ch = dispatch(self.world, "book open channel")
        self.assertTrue(ch.ok, msg=ch.message)
        self.assertIn("#general", plain(ch.message).lower() or plain(dispatch(self.world, "book pages channel").message))

        pages = plain(dispatch(self.world, "book pages channel").message)
        self.assertIn("general", pages.lower())

    def test_operator_is_player(self) -> None:
        who = plain(dispatch(self.world, "who").message)
        self.assertTrue("You" in who or "Operator" in who, msg=who)
        self.assertNotIn("Cartographer", who)
        self.assertNotIn("Builder", who)  # product avatar is Operator

    def test_layers_are_wire_workday(self) -> None:
        names = {v.name for v in self.world.list_vens()}
        self.assertIn("Wire", names)
        self.assertIn("Workday", names)
        self.assertNotIn("Material", names)
        self.assertNotIn("Memory-Archive", names)


if __name__ == "__main__":
    unittest.main()
