"""Per-instance description and lore without elevating to a new VEN."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from wbs_seed_fixtures import seed_world_story
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class InstanceDescLoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        r = dispatch(
            self.world,
            "create object Test Coin | A plain disc of copper.",
        )
        self.assertTrue(r.ok, msg=r.message)
        r = dispatch(self.world, "spawn test-coin as Coin Alpha")
        self.assertTrue(r.ok, msg=r.message)
        r = dispatch(self.world, "spawn test-coin as Coin Beta")
        self.assertTrue(r.ok, msg=r.message)

    def test_desc_override_isolates_instances(self) -> None:
        r = dispatch(
            self.world,
            "@desc on coin alpha Unique scar on Alpha only.",
        )
        self.assertTrue(r.ok, msg=r.message)

        alpha = self.world.resolve_here_named("coin alpha")
        beta = self.world.resolve_here_named("coin beta")
        assert alpha is not None and beta is not None
        self.assertEqual(alpha.description, "Unique scar on Alpha only.")
        self.assertEqual(beta.description, "A plain disc of copper.")
        self.assertIsNotNone(self.world.get_description_override(alpha.id))
        self.assertIsNone(self.world.get_description_override(beta.id))

        ex_a = plain(dispatch(self.world, "examine coin alpha").message)
        ex_b = plain(dispatch(self.world, "examine coin beta").message)
        self.assertIn("Unique scar on Alpha only.", ex_a)
        self.assertNotIn("Unique scar", ex_b)
        self.assertIn("plain disc of copper", ex_b.lower())

        # show path
        shown = plain(dispatch(self.world, "@desc on coin alpha").message)
        self.assertIn("Unique scar", shown)
        self.assertIn("instance override", shown.lower())

        # append
        r = dispatch(self.world, "@desc on coin alpha + Second line.")
        self.assertTrue(r.ok, msg=r.message)
        alpha = self.world.resolve_here_named("coin alpha")
        assert alpha is not None
        self.assertEqual(alpha.description, "Unique scar on Alpha only.\nSecond line.")

        # clear → VEN fallback
        r = dispatch(self.world, "@desc on coin alpha clear")
        self.assertTrue(r.ok, msg=r.message)
        alpha = self.world.resolve_here_named("coin alpha")
        assert alpha is not None
        self.assertIsNone(self.world.get_description_override(alpha.id))
        self.assertEqual(alpha.description, "A plain disc of copper.")
        # beta untouched throughout
        beta = self.world.resolve_here_named("coin beta")
        assert beta is not None
        self.assertEqual(beta.description, "A plain disc of copper.")

    def test_lore_on_instance_isolates_and_when_stamp(self) -> None:
        r = dispatch(
            self.world,
            "lore on coin alpha add when Before the Roads | Origin | Alpha only lore.",
        )
        self.assertTrue(r.ok, msg=r.message)
        r = dispatch(
            self.world,
            "lore on coin alpha add Pocket note | Found in the hem.",
        )
        self.assertTrue(r.ok, msg=r.message)

        alpha = self.world.resolve_here_named("coin alpha")
        beta = self.world.resolve_here_named("coin beta")
        assert alpha is not None and beta is not None
        lore_a = list(self.world.lore_for("instance", alpha.id))
        lore_b = list(self.world.lore_for("instance", beta.id))
        self.assertEqual(len(lore_a), 2)
        self.assertEqual(len(lore_b), 0)
        titles = {r["title"] for r in lore_a}
        self.assertIn("Origin", titles)
        self.assertIn("Pocket note", titles)
        origin = next(r for r in lore_a if r["title"] == "Origin")
        self.assertEqual(origin["when_label"], "Before the Roads")
        self.assertEqual(origin["body"], "Alpha only lore.")

        listed_a = plain(dispatch(self.world, "lore on coin alpha").message)
        self.assertIn("Origin", listed_a)
        self.assertIn("Before the Roads", listed_a)
        self.assertIn("Pocket note", listed_a)
        listed_b = plain(dispatch(self.world, "lore on coin beta").message)
        self.assertIn("No instance lore", listed_b)
        self.assertNotIn("Origin", listed_b)

        # examine signals related lore on A (shallow = count, not body)
        ex_a = plain(dispatch(self.world, "examine coin alpha").message)
        self.assertRegex(ex_a.lower(), r"2 related lore|record")
        self.assertNotIn("Alpha only lore.", ex_a)
        ex_b = plain(dispatch(self.world, "examine coin beta").message)
        # beta may still show 0 or only ven lore — not Alpha's instance rows
        self.assertNotIn("Origin", ex_b)

        # examine --deep prints full lore bodies
        deep_ex = plain(dispatch(self.world, "examine --deep coin alpha").message)
        self.assertIn("Origin", deep_ex)
        self.assertIn("Alpha only lore.", deep_ex)
        self.assertIn("Pocket note", deep_ex)
        self.assertIn("Found in the hem.", deep_ex)

        # in deep at … and look --deep at … are the same idea
        in_deep = plain(dispatch(self.world, "in deep at coin alpha").message)
        self.assertIn("Alpha only lore.", in_deep)
        look_deep = plain(
            dispatch(self.world, "look --deep at coin alpha").message
        )
        self.assertIn("Alpha only lore.", look_deep)
        look_trail = plain(dispatch(self.world, "look coin alpha deep").message)
        self.assertIn("Found in the hem.", look_trail)

        # undo last lore add
        dispatch(self.world, "undo")
        lore_a2 = list(self.world.lore_for("instance", alpha.id))
        self.assertEqual(len(lore_a2), 1)
        self.assertEqual(lore_a2[0]["title"], "Origin")

    def test_look_deep_place_lore(self) -> None:
        """look --deep expands place lore; plain look only hints the count."""
        r = dispatch(
            self.world,
            "lore add Founding | The hearth was raised for travelers.",
        )
        self.assertTrue(r.ok, msg=r.message)
        shallow = plain(dispatch(self.world, "look").message)
        self.assertRegex(shallow.lower(), r"record")
        self.assertNotIn("raised for travelers", shallow.lower())
        deep = plain(dispatch(self.world, "look --deep").message)
        self.assertIn("Founding", deep)
        self.assertIn("raised for travelers", deep.lower())
        deep2 = plain(dispatch(self.world, "look deep").message)
        self.assertIn("Founding", deep2)

    def test_no_elevate_required(self) -> None:
        """Instance still shares the same prime VEN after desc/lore."""
        alpha = self.world.resolve_here_named("coin alpha")
        beta = self.world.resolve_here_named("coin beta")
        assert alpha is not None and beta is not None
        self.assertEqual(alpha.ven_id, beta.ven_id)
        dispatch(self.world, "@desc on coin alpha Lived text.")
        dispatch(self.world, "lore on coin alpha add Scratch | mark")
        alpha2 = self.world.resolve_here_named("coin alpha")
        assert alpha2 is not None
        self.assertEqual(alpha2.ven_id, beta.ven_id)
        self.assertEqual(alpha2.ven_slug, beta.ven_slug)


if __name__ == "__main__":
    unittest.main()
