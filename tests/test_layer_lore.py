"""Current realm/timeline layer access: lore on realm, examine timeline, etc."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world_story
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class CurrentLayerAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        # Story seed places already have realm/timeline coords

    def test_lore_on_realm_add_and_list(self) -> None:
        add = dispatch(
            self.world,
            "lore on realm add Soft Edge | The membrane between nodes.",
        )
        self.assertTrue(add.ok, msg=add.message)
        self.assertIn("Lore on instance", plain(add.message))

        listed = dispatch(self.world, "lore on realm")
        self.assertTrue(listed.ok, msg=listed.message)
        text = plain(listed.message)
        self.assertIn("Soft Edge", text)
        self.assertIn("membrane", text)

        # shorthand
        listed2 = dispatch(self.world, "lore realm")
        self.assertTrue(listed2.ok)
        self.assertIn("Soft Edge", plain(listed2.message))

    def test_lore_on_timeline_and_examine(self) -> None:
        add = dispatch(
            self.world,
            "lore on timeline add First Hour | Clocks had not learned yet.",
        )
        self.assertTrue(add.ok, msg=add.message)
        listed = dispatch(self.world, "lore on timeline")
        self.assertIn("First Hour", plain(listed.message))

        ex = dispatch(self.world, "examine timeline")
        self.assertTrue(ex.ok, msg=ex.message)
        text = plain(ex.message)
        # layer name from seed (Told-Time / similar)
        self.assertTrue(
            "timeline" in text.lower() or "Told" in text or "Time" in text,
            msg=text,
        )

        ex_r = dispatch(self.world, "examine realm")
        self.assertTrue(ex_r.ok, msg=ex_r.message)

    def test_desc_on_realm(self) -> None:
        r = dispatch(
            self.world,
            "@desc on realm Soft fog between the woven nodes.",
        )
        self.assertTrue(r.ok, msg=r.message)
        show = dispatch(self.world, "@desc on realm")
        self.assertTrue(show.ok)
        self.assertIn("Soft fog", plain(show.message))

    def test_look_hints_layer_lore(self) -> None:
        look = plain(dispatch(self.world, "look").message)
        # Place lore count; layer lore is via lore on realm / timeline
        self.assertIn("lore", look.lower())

    def test_named_layer_still_works(self) -> None:
        # story seed has realm Woven
        r = dispatch(self.world, "lore on Woven")
        # may be empty list but should resolve
        self.assertTrue(r.ok, msg=r.message)
        self.assertNotIn("No match", plain(r.message))
        self.assertNotIn("No instance", plain(r.message).lower())

    def test_missing_layer_clear_error(self) -> None:
        # void-like: dig place without coords inheritance? clear realm
        dispatch(self.world, "realm clear")
        r = dispatch(self.world, "lore on realm")
        text = plain(r.message).lower()
        self.assertIn("no realm", text)
        self.assertIn("realm set", text)


if __name__ == "__main__":
    unittest.main()
