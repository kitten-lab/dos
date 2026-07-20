"""Tavern seed: prime kinds + named instances (Wick & Whisper)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect, get_meta
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world, seed_world_tavern
from digital_office_spaces.world import World


def _tavern_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_tavern(conn)
    return World(conn)


class TavernSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _tavern_world()

    def test_flavor_aliases(self) -> None:
        for flavor in ("tavern", "wick", "whisper", "lantern"):
            tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
            tmp.close()
            conn = connect(Path(tmp.name))
            seed_world(conn, flavor=flavor)
            w = World(conn)
            loc = w.player_location()
            assert loc is not None
            self.assertIn("WICK", loc.name.upper())
            self.assertEqual(get_meta(conn, "seed_version"), "tavern-2")

    def test_primes_are_kinds_not_unique_names(self) -> None:
        """Root VEN list should be Landing/Key/Door… not Unnumbered Landing."""
        names = {v.name for v in self.world.list_vens() if v is not None}
        self.assertIn("Landing", names)
        self.assertIn("Key", names)
        self.assertIn("Door", names)
        self.assertIn("Ledger", names)
        self.assertIn("Innkeep", names)
        self.assertNotIn("Unnumbered Landing", names)
        self.assertNotIn("Key to Rooms Not Yet Built", names)
        self.assertNotIn("Mirelle of the Last Pour", names)

    def test_start_in_common_room(self) -> None:
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Wick", look)
        self.assertIn("ledger", look.lower())
        self.assertNotIn("Hearth of Unfinished", look)
        self.assertNotIn("THE VOID", look.upper())
        loc = self.world.player_location()
        assert loc is not None
        ven = self.world.get_ven(loc.ven_id)
        assert ven is not None
        self.assertEqual(ven.name, "Tavern Room")

    def test_mirelle_and_exits(self) -> None:
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Mirelle", look)
        exits = plain(dispatch(self.world, "exits").message)
        self.assertIn("quiet booth", exits.lower())
        self.assertIn("unnumbered", exits.lower())
        self.assertIn("rumor", exits.lower())

    def test_ledger_openable_incomplete(self) -> None:
        r = dispatch(self.world, "folio open ledger")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertTrue(
            "unfinished" in text.lower()
            or "blank" in text.lower()
            or "mirelle" in text.lower(),
            msg=text,
        )
        pages = plain(dispatch(self.world, "folio pages ledger").message)
        self.assertIn("House Rules", pages)
        self.assertIn("Blank Lines", pages)
        self.assertIn("incomplete", pages.lower())

    def test_booth_chapter_and_regular(self) -> None:
        dispatch(self.world, "go into the quiet booth")
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Quiet Booth", look)
        self.assertIn("Regular", look)
        self.assertIn("Chapter", look)
        r = dispatch(self.world, "folio open chapter")
        self.assertTrue(r.ok, msg=r.message)
        body = plain(r.message)
        self.assertIn("door", body.lower())
        ch = self.world.resolve_here_named("chapter")
        assert ch is not None
        pages = self.world.list_book_pages(ch.id)
        self.assertEqual(len(pages), 2)
        titles = " ".join(str(p["title"] or "") for p in pages).lower()
        self.assertIn("your turn", titles)
        # Manuscript prime, Chapter instance
        ven = self.world.get_ven(ch.ven_id)
        assert ven is not None
        self.assertEqual(ven.name, "Manuscript")

    def test_landing_door_key_portal(self) -> None:
        dispatch(self.world, "go up the unnumbered stairs")
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Landing", look)
        self.assertIn("Key", look)
        self.assertIn("Brass Door", look)

        door = self.world.resolve_here_named("brass-door")
        key = self.world.resolve_here_named("key to rooms")
        assert door is not None and key is not None
        self.assertEqual(self.world.get_ven(door.ven_id).name, "Door")  # type: ignore[union-attr]
        self.assertEqual(self.world.get_ven(key.ven_id).name, "Key")  # type: ignore[union-attr]
        self.assertTrue(self.world.is_portal_locked(door.id))
        self.assertEqual(
            self.world.get_portal_key_instance_id(door.id), key.id
        )

        blocked = dispatch(self.world, "open brass-door")
        self.assertFalse(blocked.ok)
        self.assertIn("blank", plain(blocked.message).lower())

        self.assertTrue(
            dispatch(self.world, "unlock brass-door with key").ok
        )
        entered = dispatch(self.world, "open brass-door")
        self.assertTrue(entered.ok, entered.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Soft Suite", loc.name)
        suite_ven = self.world.get_ven(loc.ven_id)
        assert suite_ven is not None
        self.assertEqual(suite_ven.name, "Suite")


if __name__ == "__main__":
    unittest.main()
