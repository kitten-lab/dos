"""VEN specialization lineage, composition, and elevate rebind."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world_void
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_void(conn)
    return World(conn)


class LineageCreateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_create_of_parent(self) -> None:
        r0 = dispatch(self.world, "create book File | A bound sheaf of pages.")
        self.assertTrue(r0.ok, msg=r0.message)
        r1 = dispatch(
            self.world,
            "create object Secret Document of File | Classified bound file.",
        )
        self.assertTrue(r1.ok, msg=r1.message)
        self.assertIn("of", plain(r1.message).lower())

        parent = self.world.find_ven("file")
        child = self.world.find_ven("secret-document")
        assert parent is not None and child is not None
        self.assertEqual(child.parent_ven_id, parent.id)
        kids = self.world.children_of(parent.id)
        self.assertEqual([k.id for k in kids], [child.id])
        path = self.world.lineage_path(child.id)
        self.assertEqual([v.slug for v in path], [parent.slug, child.slug])

    def test_cycle_rejected(self) -> None:
        dispatch(self.world, "create book File | base")
        dispatch(self.world, "create object Secret Document of File | child")
        file_v = self.world.find_ven("file")
        secret = self.world.find_ven("secret-document")
        assert file_v and secret
        with self.assertRaises(ValueError):
            self.world.set_parent_ven(file_v.id, secret.id)


class ElevateRebindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        dispatch(self.world, "create book File | A bound sheaf.")
        dispatch(
            self.world,
            "create object Secret Document of File | Classified.",
        )
        r = dispatch(
            self.world,
            "spawn secret-document as File 13.9 - She Fell Backwards Through The Rift",
        )
        self.assertTrue(r.ok, msg=r.message)

    def test_elevate_rebinds_and_sets_parent(self) -> None:
        secret = self.world.find_ven("secret-document")
        assert secret is not None
        before = self.world.find_instances_by_name(
            "File 13.9 - She Fell Backwards Through The Rift"
        )
        self.assertEqual(len(before), 1)
        inst = before[0]
        self.assertEqual(inst.ven_id, secret.id)
        old_ref = self.world.short_ref_of(inst.id)

        r = dispatch(
            self.world,
            "elevate File 13.9 as The Rift Copy",
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("THE-RIFT-COPY", text.upper().replace(" ", "-") or text)

        elevated = self.world.find_ven("the-rift-copy")
        assert elevated is not None
        self.assertEqual(elevated.parent_ven_id, secret.id)
        self.assertIn("elevated", elevated.tags)
        self.assertNotIn("PRIME", elevated.slug)
        self.assertNotIn("-PRIME", elevated.name.upper())

        after = self.world.get_instance(inst.id)
        assert after is not None
        self.assertEqual(after.ven_id, elevated.id)
        self.assertEqual(after.ven_slug, elevated.slug)
        new_ref = self.world.short_ref_of(inst.id)
        self.assertNotEqual(new_ref, old_ref)
        self.assertTrue(new_ref.endswith("-0001") or "0001" in new_ref)

        row = self.world.conn.execute(
            "SELECT became_prime_ven_id FROM instances WHERE id = ?",
            (inst.id,),
        ).fetchone()
        self.assertEqual(row["became_prime_ven_id"], elevated.id)

        # further spawn of elevated prime
        r2 = dispatch(self.world, "spawn the-rift-copy as Another Rift Copy")
        self.assertTrue(r2.ok, msg=r2.message)
        copies = self.world.list_instances_of_ven(elevated.id)
        self.assertGreaterEqual(len(copies), 2)

    def test_elevate_default_name_skips_prime_suffix(self) -> None:
        """Bare elevate uses instance title; slug disambiguates without -PRIME."""
        dispatch(self.world, "spawn secret-document as Quiet Copy")
        r = dispatch(self.world, "elevate Quiet Copy")
        self.assertTrue(r.ok, msg=r.message)
        ven = self.world.find_ven("quiet-copy")
        assert ven is not None
        self.assertEqual(ven.name, "Quiet Copy")
        self.assertNotIn("PRIME", ven.slug)
        self.assertNotIn("PRIME", ven.name.upper())
        # Collision with origin slug uses -2 style, not -PRIME
        self.assertTrue(
            ven.slug == "QUIET-COPY" or ven.slug.startswith("QUIET-COPY-"),
            msg=ven.slug,
        )

    def test_elevate_undo_restores_origin(self) -> None:
        secret = self.world.find_ven("secret-document")
        assert secret is not None
        inst = self.world.find_instances_by_name("File 13.9")[0]
        old_id = inst.ven_id
        old_ref = self.world.short_ref_of(inst.id)

        dispatch(self.world, "elevate File 13.9 as The Rift Copy")
        elevated = self.world.find_ven("the-rift-copy")
        assert elevated is not None

        r = dispatch(self.world, "undo")
        self.assertTrue(r.ok, msg=r.message)

        restored = self.world.get_instance(inst.id)
        assert restored is not None
        self.assertEqual(restored.ven_id, old_id)
        self.assertIsNone(self.world.find_ven("the-rift-copy"))
        # short_ref restored
        self.assertEqual(self.world.short_ref_of(inst.id), old_ref)


class ComposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        dispatch(self.world, "create person Him | The idea of him.")
        dispatch(self.world, "create concept Concept of Him | Pure concept.")
        dispatch(self.world, "create archetype Archetype of Him | Pattern.")

    def test_compose_add_list_remove(self) -> None:
        r1 = dispatch(
            self.world, "compose Him + Concept of Him as concept"
        )
        self.assertTrue(r1.ok, msg=r1.message)
        r2 = dispatch(
            self.world, "compose Him + Archetype of Him as archetype"
        )
        self.assertTrue(r2.ok, msg=r2.message)

        him = self.world.find_ven("him")
        assert him is not None
        parts = self.world.list_ven_parts(him.id)
        roles = {p.role for p in parts}
        self.assertEqual(roles, {"concept", "archetype"})

        rlist = dispatch(self.world, "compose Him")
        self.assertTrue(rlist.ok, msg=rlist.message)
        text = plain(rlist.message)
        self.assertIn("Concept", text)
        self.assertIn("Archetype", text)

        r3 = dispatch(self.world, "compose Him - Concept of Him")
        self.assertTrue(r3.ok, msg=r3.message)
        parts2 = self.world.list_ven_parts(him.id)
        self.assertEqual(len(parts2), 1)
        self.assertEqual(parts2[0].role, "archetype")

    def test_examine_shows_composition(self) -> None:
        dispatch(self.world, "compose Him + Concept of Him as concept")
        dispatch(self.world, "spawn him as Elon")
        r = dispatch(self.world, "examine Elon")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Composed of", text)
        self.assertIn("Concept", text)

    def test_compose_deep_nests_parts_of_parts(self) -> None:
        """Elon → Him as archetype; Him has concept+archetype parts → deep shows both levels."""
        dispatch(self.world, "compose Him + Concept of Him as concept")
        dispatch(self.world, "compose Him + Archetype of Him as archetype")
        dispatch(self.world, "create person Elon | Builder-facing whole.")
        dispatch(self.world, "compose Elon + Him as archetype")

        shallow = plain(dispatch(self.world, "compose Elon").message)
        self.assertIn("Him", shallow)
        # Nested names not required at default depth
        self.assertNotIn("Concept of Him", shallow)

        deep = plain(dispatch(self.world, "compose Elon deep").message)
        self.assertIn("Him", deep)
        self.assertIn("Concept", deep)
        self.assertIn("Archetype", deep)
        self.assertIn("deep", deep.lower())
        # Map-style tree joints (nested under Him)
        self.assertIn("└─", deep)
        self.assertIn("├─", deep)
        # Nested children indented under Him (3 spaces or │ guide)
        self.assertTrue(
            "   ├─" in deep or "│  ├─" in deep or "   └─" in deep,
            msg=f"expected nested indent:\n{deep}",
        )

        wiki_shallow = plain(dispatch(self.world, "wiki Elon").message)
        self.assertIn("Him", wiki_shallow)
        self.assertIn("deep", wiki_shallow.lower())  # hint to expand
        self.assertTrue("├─" in wiki_shallow or "└─" in wiki_shallow)

        wiki_deep = plain(dispatch(self.world, "wiki Elon deep").message)
        self.assertIn("Him", wiki_deep)
        self.assertIn("Concept", wiki_deep)
        self.assertIn("Archetype", wiki_deep)
        self.assertIn("└─", wiki_deep)
        self.assertTrue(
            "   ├─" in wiki_deep or "│  ├─" in wiki_deep or "   └─" in wiki_deep,
            msg=f"expected nested indent on wiki deep:\n{wiki_deep}",
        )

    def test_composition_tree_cycle_safe(self) -> None:
        dispatch(self.world, "create person A | A")
        dispatch(self.world, "create person B | B")
        dispatch(self.world, "compose A + B as part")
        dispatch(self.world, "compose B + A as part")
        a = self.world.find_ven("a")
        assert a is not None
        tree = self.world.composition_tree(a.id, max_depth=4)
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0].part.part_slug, "B")
        # under B we get A marked cycle
        self.assertTrue(tree[0].children)
        self.assertTrue(tree[0].children[0].is_cycle)
        deep = plain(dispatch(self.world, "compose A deep").message)
        self.assertIn("cycle", deep.lower())


class TreeAndLineageCmdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        dispatch(self.world, "create book File | base")
        dispatch(self.world, "create object Secret Document of File | child")

    def test_vens_tree_and_lineage(self) -> None:
        rt = dispatch(self.world, "vens tree File")
        self.assertTrue(rt.ok, msg=rt.message)
        t = plain(rt.message)
        self.assertIn("FILE", t.upper())
        self.assertIn("SECRET", t.upper())

        rl = dispatch(self.world, "lineage secret-document")
        self.assertTrue(rl.ok, msg=rl.message)
        self.assertIn("›", plain(rl.message) or ">")
        self.assertIn("FILE", plain(rl.message).upper())


if __name__ == "__main__":
    unittest.main()
