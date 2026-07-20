"""Bins nested in bins: resolve by instance title, prime name, or face code."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.seed import seed_world_office
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_office(conn)
    return World(conn)


class NestedBinNameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        self.assertTrue(dispatch(self.world, "create bin Outer Cabinet").ok)
        self.assertTrue(dispatch(self.world, "create bin Inner Drawer").ok)
        self.assertTrue(dispatch(self.world, "create thing Report").ok)
        self.assertTrue(
            dispatch(self.world, "spawn outer-cabinet as Outer").ok
        )
        # Instance title shorter than prime — common spawn-as pattern
        self.assertTrue(
            dispatch(self.world, "spawn inner-drawer as Inner").ok
        )
        self.assertTrue(dispatch(self.world, "spawn report as Q1 Report").ok)
        self.assertTrue(dispatch(self.world, "put Inner in Outer").ok)

    def test_resolve_nested_by_instance_title(self) -> None:
        m = self.world.resolve_here_matches("Inner")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0].name, "Inner")

    def test_resolve_nested_by_prime_name(self) -> None:
        # Look list shows prime name in first column; must still resolve
        m = self.world.resolve_here_matches("Inner Drawer")
        self.assertEqual(len(m), 1, msg=[x.name for x in m])
        self.assertEqual(m[0].name, "Inner")

    def test_resolve_nested_by_face_code(self) -> None:
        inner = self.world.resolve_here_named("Inner")
        assert inner is not None
        code = self.world.short_ref_of(inner.id)
        m = self.world.resolve_here_matches(code)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0].id, inner.id)

    def test_put_into_nested_bin_by_name(self) -> None:
        r = dispatch(self.world, "put Q1 Report in Inner")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Q1 Report", plain(r.message))
        self.assertIn("Inner", plain(r.message))

    def test_put_into_nested_bin_by_prime_name(self) -> None:
        r = dispatch(self.world, "put Q1 Report in Inner Drawer")
        self.assertTrue(r.ok, msg=r.message)

    def test_take_from_by_prime_name(self) -> None:
        dispatch(self.world, "put Q1 Report in Inner")
        r = dispatch(self.world, "take Q1 Report from Inner Drawer")
        self.assertTrue(r.ok, msg=r.message)

    def test_find_in_container_matches_prime_and_title(self) -> None:
        outer = self.world.resolve_here_named("Outer")
        assert outer is not None
        by_title = self.world.find_in_container(outer.id, "Inner")
        by_prime = self.world.find_in_container(outer.id, "Inner Drawer")
        self.assertIsNotNone(by_title)
        self.assertIsNotNone(by_prime)
        assert by_title is not None and by_prime is not None
        self.assertEqual(by_title.id, by_prime.id)

    def test_examine_nested_by_name(self) -> None:
        r = dispatch(self.world, "examine Inner")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Inner", plain(r.message))

    def test_take_all_from_bin(self) -> None:
        self.assertTrue(dispatch(self.world, "put Q1 Report in Inner").ok)
        # also a second loose thing into Outer
        self.assertTrue(dispatch(self.world, "create thing Sticky").ok)
        self.assertTrue(dispatch(self.world, "spawn sticky as Note Pad").ok)
        self.assertTrue(dispatch(self.world, "put Note Pad in Outer").ok)
        # Outer holds: Inner (bin) + Note Pad; Inner still holds Q1 Report
        r = dispatch(self.world, "take all from Outer")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Taken all", text)
        self.assertIn("Inner", text)
        self.assertIn("Note Pad", text)
        # Report stayed inside Inner (bin taken as a unit)
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Inner", inv)
        self.assertIn("Note Pad", inv)
        # Report still in Inner
        r2 = dispatch(self.world, "take all from Inner")
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertIn("Q1 Report", plain(r2.message))
        inv2 = plain(dispatch(self.world, "inv").message)
        self.assertIn("Q1 Report", inv2)


if __name__ == "__main__":
    unittest.main()
