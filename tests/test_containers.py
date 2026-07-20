"""Nested container take/put via real dispatch."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from wbs_seed_fixtures import seed_world_classic as seed_world
from digital_office_spaces.world import World


def _seeded_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world(conn)
    return World(conn)


class NestedContainerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _seeded_world()

    def test_put_in_box_then_take_from_box_in_inventory(self) -> None:
        # Create a bin on the floor, put silver in it, pick up the bin, take silver out
        self.assertTrue(
            dispatch(self.world, "create bin Ritual Box | A small glass box.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn ritual-box").ok)
        put = dispatch(self.world, "put silver in box")
        self.assertTrue(put.ok, msg=put.message)
        self.assertIn("Put", plain(put.message))
        # silver no longer on floor — bare take should hint "from"
        take_floor = dispatch(self.world, "take silver")
        floor_msg = plain(take_floor.message).lower()
        self.assertNotIn("taken · silver", floor_msg)
        self.assertTrue(
            "from" in floor_msg or "don't see" in floor_msg or "inside" in floor_msg,
            msg=take_floor.message,
        )

        take_box = dispatch(self.world, "take box")
        self.assertIn("Taken", plain(take_box.message), msg=take_box.message)
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Inventory", inv)
        self.assertIn("Ritual Box", inv)
        self.assertIn("Silver", inv)
        # Bin bucket layout (look-style), not "holds N: …" prose
        self.assertNotIn("holds ", inv.lower())

        got = dispatch(self.world, "take silver from box")
        self.assertIn("Taken", plain(got.message), msg=got.message)
        self.assertIn("from", plain(got.message).lower())

        inv2 = plain(dispatch(self.world, "inv").message)
        self.assertIn("Silver Thread", inv2)
        # box still carried
        self.assertIn("Ritual Box", inv2)

    def test_inv_bin_buckets_like_look(self) -> None:
        """Carried bins open as placement sections; loose items under Carrying."""
        self.assertTrue(
            dispatch(self.world, "create bin Travel Pack | Canvas straps.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn travel-pack").ok)
        self.assertTrue(dispatch(self.world, "create thing Coin | Dull.").ok)
        self.assertTrue(dispatch(self.world, "spawn coin").ok)
        put = dispatch(self.world, "put silver in travel-pack")
        self.assertTrue(put.ok, msg=put.message)
        take_p = dispatch(self.world, "take travel-pack")
        self.assertTrue(take_p.ok, msg=take_p.message)
        self.assertTrue(dispatch(self.world, "take coin").ok)

        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Inventory", inv)
        self.assertIn("Carrying", inv)
        self.assertIn("Coin", inv)
        self.assertIn("Travel Pack", inv)
        self.assertIn("Silver", inv)
        # Pack is a section header; silver listed under it
        pack_at = inv.lower().find("travel pack")
        silver_at = inv.lower().find("silver")
        self.assertGreater(silver_at, pack_at, msg=inv)
        self.assertIn("inv --deep", inv.lower())

    def test_inv_deep_opens_nested_bin(self) -> None:
        """inv --deep lists contents of bins nested inside carried bins."""
        self.assertTrue(
            dispatch(self.world, "create bin Travel Pack | Canvas.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn travel-pack").ok)
        self.assertTrue(
            dispatch(self.world, "create bin Inner Pouch | Soft.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn inner-pouch").ok)
        self.assertTrue(
            dispatch(self.world, "put silver in inner-pouch").ok
        )
        self.assertTrue(
            dispatch(self.world, "put inner-pouch in travel-pack").ok
        )
        self.assertTrue(dispatch(self.world, "take travel-pack").ok)

        shallow = plain(dispatch(self.world, "inv").message)
        self.assertIn("Travel Pack", shallow)
        self.assertIn("Inner Pouch", shallow)
        # Silver is nested two levels — only with deep
        self.assertNotIn("Silver Thread", shallow)

        deep = plain(dispatch(self.world, "inv --deep").message)
        self.assertIn("Travel Pack", deep)
        self.assertIn("Inner Pouch", deep)
        self.assertIn("Silver", deep)
        # Nested bin header mark from look-style deep
        self.assertTrue(
            "└" in deep or "pouch" in deep.lower(),
            msg=deep,
        )

    def test_get_alias_and_examine_contents(self) -> None:
        dispatch(self.world, "create object Pouch | Soft.")
        dispatch(self.world, "spawn pouch")
        dispatch(self.world, "put silver in pouch")
        ex = dispatch(self.world, "examine pouch")
        self.assertTrue(ex.ok)
        self.assertIn("Silver Thread", plain(ex.message))
        dispatch(self.world, "take pouch")
        g = dispatch(self.world, "get silver from pouch")
        self.assertTrue(g.ok, msg=g.message)

    def test_put_on_and_onto_alias_in(self) -> None:
        """on / onto are the same placement as in / into (tables, trays, …)."""
        self.assertTrue(
            dispatch(self.world, "create bin Serving Tray | Flat brass.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn serving-tray").ok)
        put_on = dispatch(self.world, "put silver on tray")
        self.assertTrue(put_on.ok, msg=put_on.message)
        self.assertIn("Put", plain(put_on.message))
        ex = plain(dispatch(self.world, "examine tray").message)
        self.assertIn("Silver", ex)

        # retrieve and use onto
        dispatch(self.world, "take silver from tray")
        put_onto = dispatch(self.world, "put silver onto tray")
        self.assertTrue(put_onto.ok, msg=put_onto.message)
        ex2 = plain(dispatch(self.world, "examine tray").message)
        self.assertIn("Silver", ex2)


if __name__ == "__main__":
    unittest.main()
