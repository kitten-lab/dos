"""Inner-life sense + subtypes via create/spawn/put/examine/who (lean kinds)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import inner_life_row, plain
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.world import (
    INNER_LIFE_KINDS,
    KINDS,
    World,
    format_kind_label,
    is_inner_life_kind,
    normalize_kind,
    parse_kind_spec,
)


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class InnerLifePropTests(unittest.TestCase):
    def test_inner_life_row_fields(self) -> None:
        with_sub = plain(
            inner_life_row("Ache", "Soft Ache", "sense", "longing")
        )
        self.assertIn("Ache", with_sub)
        self.assertIn("Soft Ache", with_sub)
        self.assertIn("sense", with_sub)
        self.assertIn("longing", with_sub)
        self.assertNotIn("sense/longing", with_sub)

        no_sub = plain(
            inner_life_row("Return Want", "Desire To Return", "sense", "goal")
        )
        self.assertIn("Return Want", no_sub)
        self.assertIn("Desire To Return", no_sub)
        self.assertIn("sense", no_sub)
        self.assertIn("goal", no_sub)


class KindRegistryTests(unittest.TestCase):
    def test_lean_roots_and_inner_life(self) -> None:
        for k in (
            "person",
            "place",
            "bin",
            "thing",
            "folio",
            "symbol",
            "sense",
        ):
            self.assertIn(k, KINDS)
        self.assertIn("sense", INNER_LIFE_KINDS)
        self.assertTrue(is_inner_life_kind("sense"))
        self.assertTrue(is_inner_life_kind("person", "archetype"))
        self.assertFalse(is_inner_life_kind("thing"))
        # legacy names no longer roots
        for k in ("goal", "desire", "purpose", "feeling", "book", "object"):
            self.assertNotIn(k, KINDS)

    def test_parse_kind_spec_and_aliases(self) -> None:
        self.assertEqual(parse_kind_spec("sense"), ("sense", None))
        self.assertEqual(parse_kind_spec("feeling/longing"), ("sense", "longing"))
        self.assertEqual(parse_kind_spec("feeling:longing"), ("sense", "longing"))
        self.assertEqual(parse_kind_spec("goal"), ("sense", "goal"))
        self.assertEqual(parse_kind_spec("book"), ("folio", "book"))
        self.assertEqual(parse_kind_spec("archetype"), ("person", "archetype"))
        self.assertEqual(parse_kind_spec("object/app"), ("thing", "app"))
        self.assertEqual(format_kind_label("sense", "longing"), "sense/longing")
        self.assertEqual(normalize_kind("material", None), ("thing", "material"))


class InnerGoalsDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        r = dispatch(self.world, "go along the story road")
        self.assertTrue(r.ok, msg=r.message)

    def test_kinds_command_lists_lean_roots(self) -> None:
        r = dispatch(self.world, "kinds")
        self.assertTrue(r.ok)
        text = plain(r.message)
        self.assertIn("sense", text)
        self.assertIn("folio", text)
        self.assertIn("thing", text)
        self.assertNotIn("goal", text.split("VEN kinds:")[-1])  # not as root list

    def test_create_goal_alias_put_in_person_inner_life(self) -> None:
        r = dispatch(
            self.world,
            "create goal Desire to Return | Home as a frequency, not a place.",
        )
        self.assertTrue(r.ok, msg=r.message)
        # folds to sense/goal
        self.assertIn("sense", plain(r.message).lower())
        self.assertIn("goal", plain(r.message).lower())

        r = dispatch(self.world, "spawn desire-to-return as Return-Want")
        self.assertTrue(r.ok, msg=r.message)

        r = dispatch(self.world, "put return-want in cartographer")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("[sense]", plain(r.message).lower())

        ex = plain(dispatch(self.world, "examine cartographer").message)
        # Placement: loose senses/goals under Here (not a separate Inner life bucket)
        self.assertIn("Here", ex)
        self.assertTrue(
            "Return Want" in ex or "RETURN-WANT" in ex.upper(),
            msg=ex,
        )
        self.assertIn("DESIRE", ex.upper())
        self.assertRegex(ex, r"SNS-\d{3}-\d{4}")
        self.assertIn("Longing", ex)

        who = plain(dispatch(self.world, "who").message)
        self.assertIn("sense", who.lower())
        self.assertTrue(
            "DESIRE" in who.upper() and "RETURN" in who.upper(),
            msg=who,
        )

        dispatch(self.world, "create thing Pocket Stone | cold")
        dispatch(self.world, "spawn pocket-stone as Stone")
        dispatch(self.world, "put stone in cartographer")
        ex2 = plain(dispatch(self.world, "examine cartographer").message)
        self.assertIn("Here", ex2)
        self.assertIn("Stone", ex2)

    def test_feeling_subtype_and_desire_kind(self) -> None:
        r = dispatch(
            self.world,
            "create feeling/longing Soft Ache | A quieter cousin of longing.",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("sense/longing", plain(r.message).lower())

        ven = self.world.find_ven("soft ache")
        assert ven is not None
        self.assertEqual(ven.kind, "sense")
        self.assertEqual(ven.subtype, "longing")

        dispatch(self.world, "spawn soft-ache as Ache")
        dispatch(self.world, "put ache in cartographer")
        ex = plain(dispatch(self.world, "examine cartographer").message)
        self.assertIn("Ache", ex)
        self.assertTrue("Soft Ache" in ex or "SOFT-ACHE" in ex.upper(), msg=ex)
        self.assertIn("sense", ex.lower())
        self.assertIn("longing", ex.lower())
        # presence rows show prime · name · code (not kind/subtype)
        self.assertRegex(ex, r"SNS-\d{3}-\d{4}")

        r = dispatch(
            self.world,
            "create desire Unspoken Almost | Almost said.",
        )
        self.assertTrue(r.ok, msg=r.message)
        dispatch(self.world, "spawn unspoken-almost as Almost")
        r = dispatch(self.world, "put almost in cartographer")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("sense", plain(r.message).lower())
        ex2 = plain(dispatch(self.world, "examine cartographer").message)
        self.assertIn("sense", ex2.lower())
        self.assertIn("Almost", ex2)
        self.assertTrue(
            "Unspoken Almost" in ex2 or "UNSPOKEN" in ex2.upper(),
            msg=ex2,
        )

    def test_folio_and_thing_subtypes_allowed(self) -> None:
        r = dispatch(self.world, "create folio/codex Rock | yes")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("folio/codex", plain(r.message).lower())
        r2 = dispatch(self.world, "create thing/ore Iron | yes")
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertIn("thing/ore", plain(r2.message).lower())
        r3 = dispatch(self.world, "create object/app Pocket Terminal | soft")
        self.assertTrue(r3.ok, msg=r3.message)
        self.assertIn("thing/app", plain(r3.message).lower())


if __name__ == "__main__":
    unittest.main()
