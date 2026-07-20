"""Session undo for builder mutations."""

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


class UndoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_undo_desc(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        before = loc.description
        dispatch(self.world, "@desc Temporary text only.")
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(loc.description, "Temporary text only.")
        r = dispatch(self.world, "undo")
        self.assertTrue(r.ok)
        self.assertIn("Undone", plain(r.message))
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(loc.description, before)

    def test_undo_take(self) -> None:
        r = dispatch(self.world, "take quill")
        self.assertTrue(r.ok)
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("QUILL", inv.upper().replace("-", ""))
        # cute name may be UNFINISHED-QUILL
        self.assertTrue(
            "QUILL" in inv.upper() or "UNFINISHED" in inv.upper()
        )
        dispatch(self.world, "undo")
        inv2 = plain(dispatch(self.world, "inv").message)
        self.assertIn("nothing", inv2.lower())

    def test_undo_link(self) -> None:
        dispatch(self.world, "dig Side Alcove")
        r = dispatch(self.world, "link north -> Side Alcove both")
        self.assertTrue(r.ok)
        exits = plain(dispatch(self.world, "exits").message)
        self.assertIn("north", exits.lower())
        dispatch(self.world, "undo")
        exits2 = plain(dispatch(self.world, "exits").message)
        self.assertNotIn("north", exits2.lower())

    def test_empty_undo(self) -> None:
        r = dispatch(self.world, "undo")
        self.assertTrue(r.ok)
        self.assertIn("Nothing", plain(r.message))

    def test_undo_book_page_add(self) -> None:
        dispatch(self.world, "create book Field Notes | notebook")
        dispatch(self.world, "spawn field-notes")
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        self.assertEqual(len(self.world.list_book_pages(book.id)), 0)
        r = dispatch(self.world, "book page add field-notes A | hello")
        self.assertTrue(r.ok, msg=r.message)
        self.assertEqual(len(self.world.list_book_pages(book.id)), 1)
        r = dispatch(self.world, "undo")
        self.assertTrue(r.ok)
        self.assertIn("Undone", plain(r.message))
        self.assertEqual(len(self.world.list_book_pages(book.id)), 0)

    def test_undo_book_line_insert_remove_move(self) -> None:
        from dos.book import split_page_lines

        dispatch(self.world, "create book Field Notes | notebook")
        dispatch(self.world, "spawn field-notes")
        dispatch(self.world, r"book page add field-notes P | A\nB\nC")
        book = self.world.resolve_here_named("field-notes")
        assert book is not None

        dispatch(self.world, "book line insert field-notes 1 2 X")
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["A", "X", "B", "C"])
        dispatch(self.world, "undo")
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["A", "B", "C"])

        dispatch(self.world, "book line remove field-notes 1 2")
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["A", "C"])
        dispatch(self.world, "undo")
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["A", "B", "C"])

        dispatch(self.world, "book line move field-notes 1 3 1")
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["C", "A", "B"])
        dispatch(self.world, "undo")
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["A", "B", "C"])

    def test_undo_book_incomplete_flag(self) -> None:
        dispatch(self.world, "create book Field Notes | notebook")
        dispatch(self.world, "spawn field-notes")
        dispatch(self.world, "book page add field-notes A | x")
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        self.assertFalse(self.world.book_incomplete(book.id))
        dispatch(self.world, "book incomplete field-notes")
        self.assertTrue(self.world.book_incomplete(book.id))
        dispatch(self.world, "undo")
        self.assertFalse(self.world.book_incomplete(book.id))


if __name__ == "__main__":
    unittest.main()
