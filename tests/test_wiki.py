"""Wiki dossier: real VEN/instance only; notes=lore; sub-links in meta."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.wiki import resolve_wiki_target
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class ResolveWikiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_missing(self) -> None:
        t = resolve_wiki_target(self.world, "No Such Entity Zzz")
        self.assertEqual(t.status, "missing")

    def test_ven_and_instance(self) -> None:
        dispatch(
            self.world,
            "create goal Desire to Return | Home as frequency.",
        )
        t = resolve_wiki_target(self.world, "Desire to Return")
        self.assertEqual(t.status, "ven")
        assert t.ven is not None
        self.assertEqual(t.ven.kind, "sense")


        dispatch(self.world, "spawn desire-to-return as Return Want")
        dispatch(self.world, "go along the story road")
        # move goal? still global
        t2 = resolve_wiki_target(self.world, "Return Want")
        self.assertEqual(t2.status, "instance")


class WikiDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_wiki_dossier_fields_and_lore_notes(self) -> None:
        r = dispatch(
            self.world,
            "create goal Desire to Return | Home as a frequency, not a place.",
        )
        self.assertTrue(r.ok, msg=r.message)
        r = dispatch(
            self.world,
            "lore ven desire-to-return add Origin | First written in the void.",
        )
        self.assertTrue(r.ok, msg=r.message)

        r = dispatch(self.world, "wiki Desire to Return")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Wiki", text)
        self.assertIn("goal", text.lower())
        self.assertIn("frequency", text.lower())
        self.assertIn("Notes", text)
        self.assertIn("Origin", text)
        self.assertIn("First written", text)
        self.assertIn("Instances", text)
        self.assertIn("Sub-links", text)
        self.assertIn("Tags", text)

    def test_wiki_missing(self) -> None:
        r = dispatch(self.world, "wiki Completely Unknown Zzz")
        self.assertTrue(r.ok)
        text = plain(r.message).lower()
        self.assertTrue("no ven" in text or "no match" in text or "matching" in text)

    def test_wiki_link_unlink(self) -> None:
        dispatch(self.world, "create goal Desire to Return | x")
        dispatch(self.world, "go along the story road")
        # cartographer is a person instance
        r = dispatch(
            self.world,
            "wiki link Desire to Return cartographer",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Wiki link", plain(r.message))

        ven = self.world.find_ven("desire to return")
        assert ven is not None
        cart = self.world.resolve_here_named("cartographer")
        assert cart is not None
        links = self.world.get_wiki_links(ven.id)
        self.assertIn(cart.ven_id, links)

        shown = plain(dispatch(self.world, "wiki Desire to Return").message)
        self.assertIn("Cartographer", shown)
        self.assertIn("Sub-links", shown)

        r = dispatch(
            self.world,
            "wiki unlink Desire to Return cartographer",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertEqual(self.world.get_wiki_links(ven.id), [])

    def test_sublink_prefers_lived_instance_title(self) -> None:
        """Prime Place + instance Herenow → sub-link reads Herenow, not Place place."""
        from digital_office_spaces.seed import seed_world_bootstrap
        from digital_office_spaces.db import connect

        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_bootstrap(conn)
        world = World(conn)
        self.assertTrue(dispatch(world, "create place Silo | grain.").ok)
        self.assertTrue(
            dispatch(world, "wiki link Silo Herenow").ok
        )
        shown = plain(dispatch(world, "wiki Silo").message)
        self.assertIn("Herenow", shown)
        self.assertIn("Sub-links", shown)
        # Not the old triple-place glitch as the only label
        sub_block = shown.split("Sub-links", 1)[-1]
        self.assertIn("Herenow", sub_block)
        self.assertRegex(sub_block, r"Herenow")
        self.assertIn("Place", sub_block)  # prime whispered in meta

    def test_wiki_book_hint(self) -> None:
        dispatch(self.world, "go along the story road")
        # no book on overlook by default in story - create one
        dispatch(self.world, "create book Quiet Tome | soft pages")
        dispatch(self.world, "spawn quiet-tome as Tome")
        r = dispatch(self.world, "wiki Quiet Tome")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message).lower()
        self.assertIn("book", text)
        self.assertIn("book open", text)

    def test_wiki_opens_soft_reader_flag(self) -> None:
        r = dispatch(self.world, "wiki")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIsNotNone(r.open_wiki)
        assert r.open_wiki is not None
        label, deep = r.open_wiki
        self.assertFalse(deep)
        self.assertTrue(label)
        # Full dossier still in message for REPL
        self.assertIn("Wiki", plain(r.message))
        miss = dispatch(self.world, "wiki Completely Unknown Zzz")
        self.assertIsNone(miss.open_wiki)

    def test_wiki_default_here(self) -> None:
        r = dispatch(self.world, "wiki")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Wiki", text)
        self.assertIn("Hearth", text)


if __name__ == "__main__":
    unittest.main()
