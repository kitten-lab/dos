"""Compact VEN codes: RLM-001, OBJ-014 — typeable beside long cute slugs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect, init_schema
from digital_office_spaces.format import plain
from digital_office_spaces.ids import format_ven_code, kind_code_prefix, parse_ven_code
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.world import World


class VenCodeUnitTests(unittest.TestCase):
    def test_parse_and_format(self) -> None:
        self.assertEqual(parse_ven_code("rlm-1"), "RLM-001")
        self.assertEqual(parse_ven_code("RLM-014"), "RLM-014")
        self.assertEqual(parse_ven_code("obj014"), "OBJ-014")
        self.assertIsNone(parse_ven_code("FIELD-NOTES"))
        self.assertEqual(format_ven_code("RLM", 4), "RLM-004")
        self.assertEqual(kind_code_prefix("realm"), "RLM")
        self.assertEqual(kind_code_prefix("timeline"), "TLN")


class VenCodeWorldTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_story(conn)
        self.world = World(conn)

    def test_create_allocates_code(self) -> None:
        r = dispatch(self.world, "create object Widget Z")
        self.assertTrue(r.ok, r.message)
        msg = plain(r.message)
        self.assertRegex(msg, r"code THG-\d{3}")

        ven = self.world.find_ven("Widget Z")
        assert ven is not None
        self.assertIsNotNone(ven.code)
        assert ven.code is not None
        self.assertTrue(ven.code.startswith("THG-"))

    def test_find_by_code(self) -> None:
        dispatch(self.world, "create object Code Target")
        ven = self.world.find_ven("Code Target")
        assert ven is not None and ven.code
        found = self.world.find_ven(ven.code)
        assert found is not None
        self.assertEqual(found.id, ven.id)
        found2 = self.world.find_ven(ven.code.lower().replace("-", ""))
        # obj014 style via parse
        self.assertIsNotNone(self.world.find_ven(ven.code.replace("-", "").lower()))

    def test_instance_short_ref_uses_code(self) -> None:
        dispatch(self.world, "create object Pocket Gadget")
        dispatch(self.world, "spawn pocket-gadget")
        inst = self.world.resolve_here_named("gadget")
        assert inst is not None
        ref = self.world.short_ref_of(inst.id)
        self.assertRegex(ref, r"^THG-\d{3}-\d{4}$")


    def test_seed_backfill_has_codes(self) -> None:
        realms = self.world.list_vens("realm")
        self.assertGreater(len(realms), 0)
        for v in realms:
            self.assertIsNotNone(v.code, msg=v.name)
            assert v.code is not None
            self.assertTrue(v.code.startswith("RLM-"), msg=v.code)

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
        self.assertRegex(text, r"RLM-\d{3}")
        # blank before helper
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
        # No full catalog of named primes
        self.assertNotIn("CODE", text)
        self.assertNotIn("SLUG", text)
        # alias
        r2 = dispatch(self.world, "vens type")
        self.assertTrue(r2.ok)
        self.assertIn("VEN types", plain(r2.message))

    def test_migrate_old_db_without_code_column(self) -> None:
        """Old worlds get codes on open."""
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        path = Path(tmp.name)
        conn = connect(path)
        # Minimal pre-code schema
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
        self.assertEqual(woven.code, "RLM-001")
        self.assertEqual(mail.code, "OBJ-001")


if __name__ == "__main__":
    unittest.main()
