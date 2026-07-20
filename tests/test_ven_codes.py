"""VEN codes: DOS office faces (slug3-hex) + legacy parse helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect, init_schema
from dos.format import plain
from dos.ids import (
    format_ven_code,
    is_office_ven_code,
    kind_code_prefix,
    parse_ven_code,
)
from wbs_seed_fixtures import seed_world_story
from dos.world import World


class VenCodeUnitTests(unittest.TestCase):
    def test_parse_and_format_legacy(self) -> None:
        self.assertEqual(parse_ven_code("rlm-1"), "RLM-001")
        self.assertEqual(parse_ven_code("RLM-014"), "RLM-014")
        self.assertEqual(parse_ven_code("obj014"), "OBJ-014")
        self.assertIsNone(parse_ven_code("FIELD-NOTES"))
        self.assertEqual(format_ven_code("RLM", 4), "RLM-004")
        self.assertEqual(kind_code_prefix("realm"), "RLM")
        self.assertEqual(kind_code_prefix("timeline"), "TLN")

    def test_parse_office(self) -> None:
        self.assertEqual(parse_ven_code("COM-7F3A2C"), "com-7f3a2c")
        self.assertTrue(is_office_ven_code("com-7f3a2c"))


class VenCodeWorldTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_story(conn)
        self.world = World(conn)

    def test_create_allocates_office_code(self) -> None:
        r = dispatch(self.world, "create object Widget Z")
        self.assertTrue(r.ok, r.message)
        msg = plain(r.message)
        self.assertRegex(msg, r"code [a-z0-9]{2,4}-[0-9a-f]{6}")

        ven = self.world.find_ven("Widget Z")
        assert ven is not None
        self.assertIsNotNone(ven.code)
        assert ven.code is not None
        self.assertTrue(is_office_ven_code(ven.code), msg=ven.code)
        self.assertTrue(ven.code.startswith("wid-"))

    def test_find_by_code(self) -> None:
        dispatch(self.world, "create object Code Target")
        ven = self.world.find_ven("Code Target")
        assert ven is not None and ven.code
        found = self.world.find_ven(ven.code)
        assert found is not None
        self.assertEqual(found.id, ven.id)
        found2 = self.world.find_ven(ven.code.upper())
        assert found2 is not None
        self.assertEqual(found2.id, ven.id)

    def test_instance_short_ref_uses_office_code(self) -> None:
        dispatch(self.world, "create object Pocket Gadget")
        dispatch(self.world, "spawn pocket-gadget")
        inst = self.world.resolve_here_named("gadget")
        assert inst is not None
        ref = self.world.short_ref_of(inst.id)
        self.assertTrue(is_office_ven_code(ref), msg=ref)
        self.assertNotIn(".1", ref)
        # second spawn → .2
        dispatch(self.world, "spawn pocket-gadget as Other Gadget")
        other = self.world.resolve_here_named("Other Gadget")
        assert other is not None
        ref2 = self.world.short_ref_of(other.id)
        self.assertTrue(ref2.endswith(".2"), msg=ref2)

    def test_seed_backfill_has_office_codes(self) -> None:
        realms = self.world.list_vens("realm")
        self.assertGreater(len(realms), 0)
        for v in realms:
            self.assertIsNotNone(v.code, msg=v.name)
            assert v.code is not None
            self.assertTrue(is_office_ven_code(v.code), msg=v.code)

    def test_vens_list_table(self) -> None:
        r = dispatch(self.world, "vens realm")
        self.assertTrue(r.ok, r.message)
        text = plain(r.message)
        self.assertIn("Prime VENs · realm", text)
        self.assertIn("CODE", text)
        self.assertIn("NAME", text)
        self.assertIn("KIND", text)
        self.assertIn("SUB", text)
        self.assertIn("INST", text)
        self.assertRegex(
            text, r"CODE\s+NAME\s+KIND\s+SUB\s+INST\s+OF\s+SLUG\n\s+-+"
        )
        self.assertRegex(text, r"[a-z0-9]{2,4}-[0-9a-f]{6}")
        self.assertRegex(text, r"\n\ninstances ")

    def test_vens_types_census(self) -> None:
        """vens types shows kind/sub only — no prime names."""
        r = dispatch(self.world, "vens types")
        self.assertTrue(r.ok, r.message)
        text = plain(r.message)
        self.assertIn("VEN types", text)
        self.assertIn("KIND", text)
        self.assertIn("SUB", text)
        self.assertIn("PRIMES", text)
        self.assertIn("place", text.lower())
        self.assertNotIn("CODE", text)
        self.assertNotIn("SLUG", text)
        r2 = dispatch(self.world, "vens type")
        self.assertTrue(r2.ok)
        self.assertIn("VEN types", plain(r2.message))

    def test_migrate_old_db_without_code_column(self) -> None:
        """Old worlds get office face codes on open."""
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        path = Path(tmp.name)
        conn = connect(path)
        conn.executescript(
            """
            CREATE TABLE vens (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_prime INTEGER NOT NULL DEFAULT 1,
                elevated_from_instance_id TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO vens(id, slug, name, kind) VALUES
              ('ven_a', 'WOVEN', 'Woven', 'realm'),
              ('ven_b', 'MAIL', 'Mail', 'object');
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        conn.commit()
        conn.close()
        conn = connect(path)
        init_schema(conn)
        w = World(conn)
        woven = w.get_ven("ven_a")
        mail = w.get_ven("ven_b")
        assert woven is not None and mail is not None
        assert woven.code and mail.code
        self.assertTrue(is_office_ven_code(woven.code), msg=woven.code)
        self.assertTrue(is_office_ven_code(mail.code), msg=mail.code)
        self.assertTrue(woven.code.startswith("wov-"))
        self.assertTrue(mail.code.startswith("mai-"))


if __name__ == "__main__":
    unittest.main()
