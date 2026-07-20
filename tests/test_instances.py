"""Instance identity: short refs (SLUG-NNNN), disambiguation, spawn as, rename."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.ids import (
    format_instance_ref,
    format_instance_short_ref,
    parse_instance_ref_token,
    parse_resolve_query,
)
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.world import World

# Compact instance ref: FOL-001-0001 (VEN code + 4-digit copy)
COMPOSITE = re.compile(r"^[A-Z]{3}-\d{3}-\d{4}$")


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class ParseResolveQueryTests(unittest.TestCase):
    def test_where_and_ref(self) -> None:
        self.assertEqual(
            parse_resolve_query("field-notes inv"),
            ("field-notes", "inv", None),
        )
        self.assertEqual(
            parse_resolve_query("field-notes here"),
            ("field-notes", "here", None),
        )
        self.assertEqual(
            parse_resolve_query("field-notes#0002"),
            ("field-notes", None, "0002"),
        )
        self.assertEqual(
            parse_resolve_query("field-notes #3 inv"),
            ("field-notes", "inv", "0003"),
        )
        self.assertEqual(
            parse_resolve_query("field-notes#FIELD-NOTES-0002"),
            ("field-notes", None, "FIELD-NOTES-0002"),
        )
        self.assertEqual(
            parse_resolve_query("FIELD-NOTES-0001"),
            ("", None, "FIELD-NOTES-0001"),
        )


class FormatRefTests(unittest.TestCase):
    def test_format_digits_and_composite(self) -> None:
        self.assertEqual(format_instance_ref(1), "0001")
        self.assertEqual(format_instance_ref(12), "0012")
        self.assertEqual(
            format_instance_short_ref("field notes", 1), "FIELD-NOTES-0001"
        )
        self.assertEqual(
            format_instance_short_ref("FANCY-QUILL", 74), "FANCY-QUILL-0074"
        )
        self.assertEqual(
            parse_instance_ref_token("#FIELD-NOTES-0002"), "FIELD-NOTES-0002"
        )
        self.assertEqual(parse_instance_ref_token("#1"), "0001")
        # Soft separators: spaces / underscores like dashes
        from digital_office_spaces.ids import parse_ven_code, parse_resolve_query

        self.assertEqual(parse_ven_code("bin 3"), "BIN-003")
        self.assertEqual(parse_ven_code("BIN 003"), "BIN-003")
        self.assertEqual(
            parse_instance_ref_token("bin 003 0043"), "BIN-003-0043"
        )
        self.assertEqual(
            parse_instance_ref_token("BIN-003-0043"), "BIN-003-0043"
        )
        base, where, ref = parse_resolve_query("bin 003 0043")
        self.assertEqual(base, "")
        self.assertEqual(ref, "BIN-003-0043")
        # multi-word names still names, not codes
        base2, _, ref2 = parse_resolve_query("Quiet Invitation")
        self.assertEqual(base2, "Quiet Invitation")
        self.assertIsNone(ref2)


class InstanceIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        self.assertTrue(
            dispatch(self.world, "create book Field Notes | blank").ok
        )

    def test_spawn_as_and_sequential_slug_refs(self) -> None:
        r1 = dispatch(self.world, "spawn field-notes as Ritual Notes")
        self.assertTrue(r1.ok, msg=r1.message)
        msg1 = plain(r1.message)
        self.assertRegex(msg1, r"FOL-\d{3}-0001")
        self.assertIn("Ritual Notes", msg1)

        r2 = dispatch(self.world, "spawn field-notes as Pocket Notes")
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertRegex(plain(r2.message), r"FOL-\d{3}-0002")

        ven = self.world.find_ven("field-notes")
        assert ven is not None
        insts = self.world.list_instances_of_ven(ven.id)
        refs = sorted(self.world.short_ref_of(i.id) for i in insts)
        self.assertEqual(len(refs), 2)
        self.assertTrue(refs[0].endswith("-0001"))
        self.assertTrue(refs[1].endswith("-0002"))
        for ref in refs:
            self.assertRegex(ref, COMPOSITE)

    def test_soft_spaced_code_resolves_take(self) -> None:
        """``take bin 001 0001`` finds BIN-001-0001 on the floor."""
        self.assertTrue(dispatch(self.world, "dig bin Soft Shelf | x").ok)
        inst = self.world.resolve_here_named("soft shelf")
        assert inst is not None
        ref = self.world.short_ref_of(inst.id)
        self.assertRegex(ref, r"^BIN-\d{3}-0001$")
        # spaced form of the same code
        soft = ref.replace("-", " ")
        hit = self.world.resolve_here_named(soft)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.id, inst.id)
        r = dispatch(self.world, f"take {soft}")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Taken", plain(r.message))

    def test_ambiguous_room_and_inv(self) -> None:
        dispatch(self.world, "spawn field-notes as Ritual Notes")
        dispatch(self.world, "take ritual")
        dispatch(self.world, "spawn field-notes as Pocket Notes")
        r = dispatch(self.world, "book pages field-notes")
        text = plain(r.message)
        self.assertIn("Ambiguous", text)
        self.assertRegex(text, r"FOL-\d{3}-0001")
        self.assertRegex(text, r"FOL-\d{3}-0002")
        self.assertIn("inv", text.lower())
        self.assertIn("here", text.lower())

        r_inv = dispatch(
            self.world, "book page add field-notes inv Intro | From pack."
        )
        self.assertTrue(r_inv.ok, msg=r_inv.message)
        self.assertNotIn("Ambiguous", plain(r_inv.message))

        r_here = dispatch(
            self.world, "book page add field-notes here Intro | From floor."
        )
        self.assertTrue(r_here.ok, msg=r_here.message)

        # by digit suffix after name
        r_ref = dispatch(self.world, "book pages field-notes#0001")
        self.assertNotIn("Ambiguous", plain(r_ref.message))
        self.assertIn("page", plain(r_ref.message).lower())

        # by full compact composite
        ven = self.world.find_ven("field-notes")
        assert ven is not None
        code_ref = f"{ven.code}-0001"
        r_comp = dispatch(self.world, f"book pages field-notes#{code_ref}")
        self.assertNotIn("Ambiguous", plain(r_comp.message))
        self.assertIn("page", plain(r_comp.message).lower())
        # legacy cute-slug ref still resolves
        r_legacy = dispatch(
            self.world, "book pages field-notes#FIELD-NOTES-0001"
        )
        self.assertNotIn("Ambiguous", plain(r_legacy.message))

    def test_examine_shows_slug_ref(self) -> None:
        dispatch(self.world, "spawn field-notes as Ritual Notes")
        r = dispatch(self.world, "examine ritual")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertRegex(text, r"FOL-\d{3}-0001")
        self.assertIn("Ritual Notes", text)

    def test_resolve_by_composite_alone(self) -> None:
        dispatch(self.world, "spawn field-notes as Ritual Notes")
        dispatch(self.world, "spawn field-notes as Pocket Notes")
        # New compact code form
        ven = self.world.find_ven("field-notes")
        assert ven is not None
        r = dispatch(self.world, f"examine {ven.code}-0002")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Pocket Notes", text)
        self.assertRegex(text, r"FOL-\d{3}-0002")
        # Legacy cute slug form still works
        r2 = dispatch(self.world, "examine FIELD-NOTES-0002")
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertIn("Pocket Notes", plain(r2.message))

    def test_instances_command(self) -> None:
        dispatch(self.world, "spawn field-notes as Ritual Notes")
        dispatch(self.world, "spawn field-notes as Pocket Notes")
        listed = plain(dispatch(self.world, "instances field-notes").message)
        self.assertIn("Ritual Notes", listed)
        self.assertIn("Pocket Notes", listed)
        self.assertRegex(listed, r"FOL-\d{3}-0001")
        self.assertRegex(listed, r"FOL-\d{3}-0002")

    def test_rename(self) -> None:
        dispatch(self.world, "spawn field-notes as Pocket Notes")
        r = dispatch(self.world, "rename pocket as Travel Notes")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Travel Notes", plain(r.message))
        listed = plain(dispatch(self.world, "instances field-notes").message)
        self.assertIn("Travel Notes", listed)

    def test_rename_arrow_title(self) -> None:
        dispatch(self.world, "spawn field-notes as Pocket Notes")
        r = dispatch(self.world, "rename pocket -> Field Journal")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Field Journal", plain(r.message))
        r2 = dispatch(self.world, "rename field → Pack Notes")
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertIn("Pack Notes", plain(r2.message))

    def test_rename_here_place(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        prior = loc.name
        r = dispatch(self.world, "rename here as Quiet Testing Gallery")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Quiet Testing Gallery", plain(r.message))
        loc2 = self.world.player_location()
        assert loc2 is not None
        self.assertEqual(loc2.name, "Quiet Testing Gallery")
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Quiet Testing Gallery", look)
        # undo restores prior display title
        self.assertTrue(dispatch(self.world, "undo").ok)
        loc3 = self.world.player_location()
        assert loc3 is not None
        self.assertEqual(loc3.name, prior)

    def test_rename_place_by_name(self) -> None:
        self.assertTrue(dispatch(self.world, "dig Side Alcove").ok)
        r = dispatch(self.world, "rename Side Alcove as Memory Nook")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Memory Nook", plain(r.message))
        places = self.world.find_instances_by_name("Memory Nook", kind="place")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0].name, "Memory Nook")
        # Still findable by original dig / prime name
        by_old = self.world.find_instances_by_name("Side Alcove", kind="place")
        self.assertEqual(len(by_old), 1)

    def test_bare_spawn_auto_suffix(self) -> None:
        dispatch(self.world, "spawn field-notes as First")
        r = dispatch(self.world, "spawn field-notes")
        self.assertTrue(r.ok, msg=r.message)
        msg = plain(r.message)
        self.assertRegex(msg, r"FOL-\d{3}-0002")
        self.assertIn("Field Notes", msg)


if __name__ == "__main__":
    unittest.main()
