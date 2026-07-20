"""Formal VEN names + cute slugs via shipped create/seed/dispatch paths."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.ids import (
    cute_name,
    display_name,
    is_cute_name,
    names_match,
    normalize_formal_name,
    normalize_instance_title,
)
from digital_office_spaces.seed import seed_world_classic as seed_world
from digital_office_spaces.seed import seed_world_story
from digital_office_spaces.world import World

CUTE = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*$")


def _seeded_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world(conn)
    return World(conn)


def _story_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class CuteNameUnitTests(unittest.TestCase):
    def test_cute_name_shapes(self) -> None:
        self.assertEqual(cute_name("Silver Thread"), "SILVER-THREAD")
        self.assertEqual(cute_name("prime"), "PRIME")
        self.assertEqual(
            cute_name("Hall of Shelved Years (Shattered)"),
            "HALL-OF-SHELVED-YEARS-SHATTERED",
        )

    def test_names_match_whole_token_not_substring(self) -> None:
        # whole token still works (take silver → Silver Thread)
        self.assertTrue(names_match("silver", "Silver Thread"))
        self.assertTrue(names_match("Silver Thread", "SILVER-THREAD"))
        self.assertTrue(names_match("field notes", "Field Notes"))
        # game code: q1 must not partial-hit Q1G1
        self.assertFalse(names_match("q1", "Q1G1"))
        self.assertFalse(names_match("Q1", "Q1G1 Schedule"))
        self.assertTrue(names_match("Q1G1", "Q1G1"))
        self.assertTrue(names_match("q1g1", "Q1G1 Schedule"))  # whole token
        self.assertTrue(is_cute_name("SILVER-THREAD"))
        self.assertFalse(is_cute_name("Silver Thread"))

    def test_cute_name_strips_apostrophe_without_space_token(self) -> None:
        """Apostrophe must not become a dash (Chester S); strip for slug."""
        self.assertEqual(cute_name("Chester's"), "CHESTERS")
        self.assertEqual(cute_name("CHESTER'S"), "CHESTERS")
        self.assertEqual(cute_name('Say "Hi"'), "SAY-HI")
        self.assertEqual(cute_name("pre-war"), "PRE-WAR")
        self.assertNotEqual(cute_name("Chester's"), "CHESTER-S")

    def test_formal_name_preserves_case_and_punctuation(self) -> None:
        self.assertEqual(normalize_formal_name("Chester's"), "Chester's")
        self.assertEqual(normalize_formal_name("CHESTER'S"), "CHESTER'S")
        self.assertEqual(normalize_formal_name("Terminal IO"), "Terminal IO")
        self.assertEqual(normalize_formal_name('Note "alpha"'), 'Note "alpha"')
        self.assertEqual(normalize_formal_name("pre-war map"), "pre-war map")
        self.assertEqual(display_name("Chester's"), "Chester's")
        self.assertEqual(display_name("Terminal IO"), "Terminal IO")
        # Must not title-case apostrophe-adjacent letter into separate token
        self.assertNotEqual(display_name("Chester's"), "Chester S")
        self.assertNotIn("Chester S", display_name("Chester's"))
        # Multi-cap token stays as stored (not Io)
        self.assertEqual(display_name("Terminal IO"), "Terminal IO")
        self.assertNotEqual(display_name("Terminal IO"), "Terminal Io")


class NamingCreateAndSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _seeded_world()

    def test_create_ven_formal_name_and_cute_slug(self) -> None:
        r = dispatch(
            self.world,
            "create material Moon Filament | Thin light that remembers tides.",
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Moon Filament", text)
        self.assertIn("MOON-FILAMENT", text)  # slug still shown
        ven = self.world.find_ven("moon filament")
        self.assertIsNotNone(ven)
        assert ven is not None
        self.assertEqual(ven.name, "Moon Filament")
        self.assertEqual(ven.slug, "MOON-FILAMENT")
        self.assertRegex(ven.slug, CUTE.pattern)
        self.assertFalse(is_cute_name(ven.name))

    def test_create_ven_apostrophe_and_multicap(self) -> None:
        r = dispatch(
            self.world,
            "create person Chester's | Keeper of the apostrophe.",
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Chester's", text)
        self.assertNotIn("Chester S", text)
        ven = self.world.find_ven("chesters")
        self.assertIsNotNone(ven)
        assert ven is not None
        self.assertEqual(ven.name, "Chester's")
        self.assertEqual(ven.slug, "CHESTERS")
        self.assertEqual(display_name(ven.name), "Chester's")

        # ALL-CAPS formal with apostrophe
        r2 = dispatch(
            self.world,
            "create object CHESTER'S RELIC | Dusty.",
        )
        self.assertTrue(r2.ok, msg=r2.message)
        v2 = self.world.find_ven("chesters relic")
        assert v2 is not None
        self.assertEqual(v2.name, "CHESTER'S RELIC")
        self.assertEqual(v2.slug, "CHESTERS-RELIC")
        self.assertEqual(display_name(v2.name), "CHESTER'S RELIC")

        r3 = dispatch(
            self.world,
            "create object Terminal IO | Multi-cap token.",
        )
        self.assertTrue(r3.ok, msg=r3.message)
        v3 = self.world.find_ven("terminal io")
        assert v3 is not None
        self.assertEqual(v3.name, "Terminal IO")
        self.assertEqual(v3.slug, "TERMINAL-IO")
        self.assertEqual(display_name(v3.name), "Terminal IO")
        self.assertNotEqual(display_name(v3.name), "Terminal Io")

        r4 = dispatch(
            self.world,
            'create object Quote-"Mark"-Hyphen | punctuation soup.',
        )
        self.assertTrue(r4.ok, msg=r4.message)
        v4 = self.world.find_ven("quote-mark-hyphen")
        assert v4 is not None
        self.assertIn('"', v4.name)
        self.assertIn("-", v4.name)
        self.assertRegex(v4.slug, CUTE.pattern)

        # find via formal and slug
        self.assertIsNotNone(self.world.find_ven("Chester's"))
        self.assertIsNotNone(self.world.find_ven("CHESTERS"))
        self.assertIsNotNone(self.world.find_ven("Terminal IO"))

    def test_seed_timeline_and_place_formal_plus_cute_slug(self) -> None:
        look = plain(dispatch(self.world, "look").message)
        where = plain(dispatch(self.world, "whereami").message)
        # player-facing: formal/seed names
        self.assertIn("The Cathedral of Ordinary Light", look)
        self.assertIn("Prime", look)
        self.assertIn("Material", look)
        self.assertIn("Silver Thread", look)
        self.assertIn("The Cathedral of Ordinary Light", where)
        self.assertIn("Prime", where)
        loc = self.world.player_location()
        assert loc is not None
        # formal place name; slug on VEN is cute
        self.assertEqual(loc.name, "The Cathedral of Ordinary Light")
        self.assertTrue(is_cute_name(loc.ven_slug))
        # timeline VEN from seed
        tl = self.world.find_ven("prime")
        self.assertIsNotNone(tl)
        assert tl is not None
        self.assertEqual(tl.kind, "timeline")
        self.assertEqual(tl.name, "Prime")
        self.assertEqual(tl.slug, "PRIME")
        self.assertTrue(is_cute_name(tl.slug))

    def test_lore_ven_and_take_resolve_relaxed_input(self) -> None:
        add = dispatch(
            self.world,
            "lore ven silver thread add Binding | Ties frayed timelines.",
        )
        self.assertTrue(add.ok, msg=add.message)
        listed = dispatch(self.world, "lore ven SILVER-THREAD")
        self.assertTrue(listed.ok)
        self.assertIn("Binding", plain(listed.message))
        take = dispatch(self.world, "take silver")
        self.assertTrue(take.ok, msg=take.message)
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Silver Thread", inv)

    def test_go_still_works_after_cute_seed(self) -> None:
        r = dispatch(self.world, "go through the mirror")
        self.assertTrue(r.ok)
        text = plain(r.message)
        self.assertIn("Hall of Shelved Years", text)
        self.assertIn("Memory-Archive", text)


class InstanceDisplayTitleTests(unittest.TestCase):
    """Instance spawn/rename keep CAPS and separators (- /); resolve still works."""

    def setUp(self) -> None:
        self.world = _story_world()
        r = dispatch(self.world, "create book Field Notes | Working notebook.")
        self.assertTrue(r.ok, msg=r.message)

    def test_normalize_preserves_caps_and_separators(self) -> None:
        self.assertEqual(
            normalize_instance_title("Terminal-Prolog"), "Terminal-Prolog"
        )
        self.assertEqual(
            normalize_instance_title("Field Notes / Vol.1"),
            "Field Notes / Vol.1",
        )
        self.assertEqual(display_name("Terminal-Prolog"), "Terminal-Prolog")
        self.assertEqual(
            display_name("Field Notes / Vol.1"), "Field Notes / Vol.1"
        )
        # Matching still collapses for comparison
        self.assertEqual(
            cute_name("Terminal-Prolog"), cute_name("terminal prolog")
        )

    def test_spawn_as_hyphen_caps_title(self) -> None:
        r = dispatch(self.world, "spawn field-notes as Terminal-Prolog")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Terminal-Prolog", text)
        self.assertNotIn("TERMINAL-PROLOG", text)
        # Must not collapse to space-only title-case loss of hyphen intent
        self.assertNotIn("Terminal Prolog", text)

        book = self.world.resolve_here_named("Terminal-Prolog")
        self.assertIsNotNone(book)
        assert book is not None
        self.assertEqual(book.name, "Terminal-Prolog")
        self.assertFalse(is_cute_name(book.name))

        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Terminal-Prolog", look)

        ex = dispatch(self.world, "examine Terminal-Prolog")
        self.assertTrue(ex.ok, msg=ex.message)
        self.assertIn("Terminal-Prolog", plain(ex.message))

        # relaxed match still finds it
        ex2 = dispatch(self.world, "examine terminal prolog")
        self.assertTrue(ex2.ok, msg=ex2.message)

    def test_rename_slash_title_shows_and_resolves(self) -> None:
        r = dispatch(self.world, "spawn field-notes as Pocket Notes")
        self.assertTrue(r.ok, msg=r.message)
        r = dispatch(
            self.world, "rename pocket as Field Notes / Vol.1"
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Field Notes / Vol.1", text)
        self.assertNotIn("FIELD-NOTES-VOL-1", text)

        book = self.world.resolve_here_named("Field Notes / Vol.1")
        self.assertIsNotNone(book)
        assert book is not None
        self.assertEqual(book.name, "Field Notes / Vol.1")

        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Field Notes / Vol.1", look)

        inv = dispatch(self.world, "take field notes")
        self.assertTrue(inv.ok, msg=inv.message)
        pack = plain(dispatch(self.world, "inv").message)
        self.assertIn("Field Notes / Vol.1", pack)

        ex = dispatch(self.world, "examine Field Notes / Vol.1")
        self.assertTrue(ex.ok, msg=ex.message)
        self.assertIn("Field Notes / Vol.1", plain(ex.message))

    def test_ven_create_formal_name_cute_slug(self) -> None:
        """Prime VEN: formal name stored; slug is cute ALL-CAPS."""
        r = dispatch(
            self.world,
            "create object Moon Filament | thin light.",
        )
        self.assertTrue(r.ok, msg=r.message)
        ven = self.world.find_ven("moon filament")
        assert ven is not None
        self.assertEqual(ven.name, "Moon Filament")
        self.assertEqual(ven.slug, "MOON-FILAMENT")
        self.assertTrue(is_cute_name(ven.slug))


if __name__ == "__main__":
    unittest.main()
