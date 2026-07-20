"""Prime VEN export/import via ~/.aidm/ven-collector."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.seed import seed_world_void
from dos.ven_pack import (
    export_ven,
    find_pack,
    import_pack,
    list_packs,
    load_pack_file,
    pack_filename,
    ven_collector_dir,
    world_label,
)
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_void(conn)
    return World(conn)


class VenPackUnitTests(unittest.TestCase):
    def test_filename_order(self) -> None:
        self.assertEqual(
            pack_filename(1, "EVE-001", "THE-KNOCK"),
            "0001-EVE-001-the-knock.ven",
        )


class VenPackRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = Path(tempfile.mkdtemp())
        self.world = _world()
        self.assertTrue(
            dispatch(
                self.world,
                "create event The Knock | Three soft taps on the grain.",
            ).ok
        )
        ven = self.world.find_ven("The Knock")
        assert ven is not None
        self.world.add_lore(
            "ven",
            ven.id,
            body="It always comes at the third hour.",
            title="When",
            author="builder",
        )

    def test_export_import_round_trip(self) -> None:
        ven = self.world.find_ven("The Knock")
        assert ven is not None
        path = export_ven(
            self.world,
            ven,
            origin_world="Imported.To",
            collector=self.collector,
        )
        self.assertTrue(path.is_file())
        self.assertRegex(path.name, r"^\d{4}-EVT-\d{3}-the-knock\.ven$")

        pack = load_pack_file(path)
        self.assertEqual(pack["format"], "aidm.ven")
        self.assertEqual(pack["provenance"]["origin_world"], "Imported.To")
        self.assertEqual(pack["prime"]["name"], "The Knock")
        self.assertTrue(pack["lore"])

        # Fresh world
        other = _world()
        ven_id, code, inst_id, remap = import_pack(
            other, pack, target_world_label="Stable Build"
        )
        self.assertIsNone(remap)
        self.assertIsNone(inst_id)
        imported = other.get_ven(ven_id)
        assert imported is not None
        self.assertEqual(imported.name, "The Knock")
        self.assertEqual(imported.kind, "event")

        self.assertEqual(imported.code, ven.code)
        lore = other.lore_for("ven", ven_id)
        self.assertTrue(any("third hour" in (r["body"] or "") for r in lore))
        meta = imported.meta or {}
        self.assertEqual((meta.get("ie") or {}).get("origin_world"), "Imported.To")

    def test_dispatch_export_load(self) -> None:
        with mock.patch(
            "dos.ven_pack.ven_collector_dir",
            return_value=self.collector,
        ):
            r = dispatch(self.world, "vens export The Knock")
            self.assertTrue(r.ok, r.message)
            self.assertIn("Exported", plain(r.message))
            listed = dispatch(self.world, "ven load")
            self.assertTrue(listed.ok, listed.message)
            self.assertIn("The Knock", plain(listed.message))
            self.assertIn("VEN collector", plain(listed.message))

            other = _world()
            packs = list_packs(self.collector)
            self.assertEqual(len(packs), 1)
            imp = dispatch(other, f"ven load {packs[0].path.name}")
            self.assertTrue(imp.ok, imp.message)
            self.assertIn("Imported", plain(imp.message))
            found = other.find_ven("The Knock")
            self.assertIsNotNone(found)

    def test_code_remap_on_conflict(self) -> None:
        ven = self.world.find_ven("The Knock")
        assert ven is not None
        path = export_ven(
            self.world,
            ven,
            origin_world="Test",
            collector=self.collector,
        )
        pack = load_pack_file(path)
        # Import twice into same world — second reuses existing prime (no remap create)
        import_pack(self.world, pack, target_world_label="A")
        ven_id2, code2, _inst, remap = import_pack(
            self.world, pack, target_world_label="A"
        )
        # Same prime reused — no second create
        self.assertEqual(ven_id2, ven.id)
        self.assertIsNone(remap)
        self.assertEqual(code2, ven.code)

    def test_instance_export_import_book(self) -> None:
        from dos.ven_pack import export_instance

        self.assertTrue(
            dispatch(self.world, "create book Field Notes | notebook").ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn field-notes as Ritual Notes").ok
        )
        book = self.world.resolve_here_named("ritual")
        assert book is not None
        self.world.add_book_page(book.id, "One", "First page body.")
        path = export_instance(
            self.world,
            book,
            origin_world="Lab",
            collector=self.collector,
        )
        self.assertRegex(
            path.name, r"^\d{4}-FOL-\d{3}-\d{4}-ritual-notes\.ven$"
        )
        pack = load_pack_file(path)
        self.assertEqual(pack.get("pack_kind"), "instance")
        self.assertEqual(pack["instance"]["name_override"], "Ritual Notes")
        self.assertTrue(pack["instance"]["book_pages"])

        other = _world()
        loc = other.player_location()
        assert loc is not None
        _vid, code, inst_id, _remap = import_pack(
            other,
            pack,
            target_world_label="Stable",
            place_instance_id=loc.id,
        )
        self.assertIsNotNone(inst_id)
        assert inst_id is not None
        inst = other.get_instance(inst_id)
        assert inst is not None
        # Origin frag stamped so foreign identity survives host FOL codes
        self.assertIn("Ritual Notes", inst.name)
        self.assertIn("Lab", inst.name)
        self.assertEqual(inst.ven_kind, "folio")
        pages = other.list_book_pages(inst_id)
        self.assertEqual(len(pages), 1)
        self.assertIn("First page", pages[0]["body"] or "")
        # Sitting in the room
        look = plain(dispatch(other, "look").message)
        self.assertIn("Ritual Notes", look)
        self.assertTrue(code.startswith("FOL-"))

        # Re-import same pack: no second instance, same short ref
        _vid2, _c2, inst_id2, note = import_pack(
            other,
            pack,
            target_world_label="Stable",
            place_instance_id=loc.id,
        )
        self.assertEqual(inst_id2, inst_id)
        self.assertIsNotNone(note)
        self.assertIn("already imported", (note or "").lower())
        ven = other.find_ven("Field Notes")
        assert ven is not None
        self.assertEqual(len(other.list_instances_of_ven(ven.id)), 1)

    def test_code_collision_keeps_foreign_name(self) -> None:
        """FOL-00N in target is a different concept — do not attach as its child."""
        from dos.ven_pack import export_instance

        # Source: folio World Studio Help at whatever FOL code
        self.assertTrue(
            dispatch(
                self.world,
                "create book World Studio Help | Full help dump.",
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn dos-help").ok)
        help_book = self.world.resolve_here_named("dos-help")
        assert help_book is not None
        self.world.add_book_page(help_book.id, "Index", "help index body")
        path = export_instance(
            self.world,
            help_book,
            origin_world="Kitten-Lab",
            collector=self.collector,
        )
        pack = load_pack_file(path)
        home = pack["provenance"]["home_code"]

        # Target already has a different folio occupying that code number
        other = _world()
        other_code = home  # force same code if free, else create then rename code...
        # Create a host folio first so FOL-001 (or next) is taken
        self.assertTrue(
            dispatch(other, "create book Host Concept Book | Lab native.").ok
        )
        host = other.find_ven("Host Concept Book")
        assert host is not None
        # If pack wants same code as host, collision path triggers
        pack["prime"]["code"] = host.code
        pack["provenance"]["home_code"] = host.code

        loc = other.player_location()
        assert loc is not None
        ven_id, local_code, inst_id, remap = import_pack(
            other,
            pack,
            target_world_label="Other World",
            place_instance_id=loc.id,
        )
        self.assertIsNotNone(inst_id)
        assert inst_id is not None
        inst = other.get_instance(inst_id)
        assert inst is not None
        # Must NOT be the host prime
        self.assertNotEqual(inst.ven_id, host.id)
        self.assertIn("World Studio Help", inst.name)
        self.assertIn("Kitten-Lab", inst.name)
        # Remapped off host code
        self.assertIsNotNone(remap)
        self.assertNotEqual(local_code, host.code)
        pages = other.list_book_pages(inst_id)
        self.assertTrue(any("help index" in (p["body"] or "").lower() for p in pages))
        # Host still one concept
        self.assertEqual(host.name, "Host Concept Book")

    def test_short_ref_not_collided_on_fresh_instance(self) -> None:
        """If 0001 is taken, import still works with next digits."""
        from dos.ven_pack import export_instance

        self.assertTrue(dispatch(self.world, "create book Ledger").ok)
        self.assertTrue(dispatch(self.world, "spawn ledger as Alpha").ok)
        a = self.world.resolve_here_named("alpha")
        assert a is not None
        path = export_instance(
            self.world, a, origin_world="Lab", collector=self.collector
        )
        pack = load_pack_file(path)

        other = _world()
        # Seed a BOK prime with 0001 already used
        self.assertTrue(dispatch(other, "create book Ledger").ok)
        self.assertTrue(dispatch(other, "spawn ledger as Seeded").ok)
        loc = other.player_location()
        assert loc is not None
        _vid, _code, inst_id, _n = import_pack(
            other,
            pack,
            target_world_label="Stable",
            place_instance_id=loc.id,
        )
        assert inst_id is not None
        ref = other.short_ref_of(inst_id)
        # Must not share 0001 with Seeded
        seeded = other.resolve_here_named("seeded")
        assert seeded is not None
        self.assertNotEqual(
            other.short_ref_of(inst_id), other.short_ref_of(seeded.id)
        )
        self.assertRegex(ref, r"FOL-\d{3}-\d{4}")



if __name__ == "__main__":
    unittest.main()
