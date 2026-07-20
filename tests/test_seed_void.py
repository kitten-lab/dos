"""Void seed: blank canvas place + one strange romantic book."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world, seed_world_void
from digital_office_spaces.world import World


def _void_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_void(conn)
    return World(conn)


class VoidSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _void_world()

    def test_seed_world_flavor_void(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world(conn, flavor="void")
        w = World(conn)
        loc = w.player_location()
        assert loc is not None
        self.assertIn("VOID", loc.name.upper())

    def test_start_in_void_no_exits_no_tour(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("VOID", loc.name.upper())
        self.assertEqual(len(self.world.exits(loc.id)), 0)

        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Void", look)
        # not the story/classic tour
        self.assertNotIn("Hearth", look)
        self.assertNotIn("Cathedral", look)
        self.assertNotIn("mirror", look.lower())

        exits = plain(dispatch(self.world, "exits").message)
        self.assertIn("No paths", exits)
        paths = plain(dispatch(self.world, "paths").message)
        self.assertIn("No paths", paths)
        ways = plain(dispatch(self.world, "ways").message)
        self.assertIn("No paths", ways)

        # only one place instance (the void)
        places = [
            i
            for i in self.world.list_instances_of_ven(loc.ven_id)
        ]
        self.assertEqual(len(places), 1)

    def test_book_present_openable_romantic(self) -> None:
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Book", look)
        self.assertTrue(
            "Loves You Backwards" in look or "loves you backwards" in look.lower(),
            msg=look,
        )

        r = dispatch(self.world, "book open loves")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("beloved", text.lower())
        self.assertIn("pages", text.lower())  # or page content
        # romantic / strange cues from seed pages
        self.assertTrue(
            "kiss" in text.lower()
            or "beloved" in text.lower()
            or "maps" in text.lower()
            or "lonely" in text.lower()
            or "blush" in text.lower(),
            msg=text,
        )

        pages_msg = plain(dispatch(self.world, "book pages loves").message)
        self.assertIn("Invocation", pages_msg)
        self.assertIn("How Worlds Begin", pages_msg)
        self.assertIn("incomplete", pages_msg.lower())

        book = self.world.resolve_here_named("loves")
        assert book is not None
        pages = self.world.list_book_pages(book.id)
        self.assertEqual(len(pages), 2)
        bodies = "\n".join(p["body"] for p in pages)
        self.assertIn("Beloved stranger", bodies)
        self.assertIn("kiss withheld", bodies)

    def test_who_is_only_builder(self) -> None:
        who = plain(dispatch(self.world, "who").message)
        self.assertIn("Builder", who)
        self.assertNotIn("Cartographer", who)
        self.assertNotIn("Archivist", who)


if __name__ == "__main__":
    unittest.main()
