"""Lost Dept: soft despawn / reclaim / list."""

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


class LostDeptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        self.assertTrue(
            dispatch(self.world, "create object Spare Token | Junk for tests.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn spare-token").ok)
        self.assertTrue(dispatch(self.world, "take spare").ok)

    def test_despawn_to_lost_dept_and_reclaim(self) -> None:
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Spare Token", inv)

        r = dispatch(self.world, "despawn spare token")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Lost", text)
        self.assertIn("Lost Dept", text)

        inv2 = plain(dispatch(self.world, "inv").message)
        self.assertNotIn("Spare Token", inv2)

        lost = plain(dispatch(self.world, "lost").message)
        self.assertIn("Lost Dept", lost)
        self.assertIn("Spare Token", lost)

        # instance still exists
        hits = self.world.find_instances_by_name("Spare Token")
        self.assertEqual(len(hits), 1)
        cont = self.world.container_of(hits[0].id)
        assert cont is not None
        self.assertTrue(self.world.is_lost_dept(cont[0]))

        rec = dispatch(self.world, "reclaim spare token")
        self.assertTrue(rec.ok, msg=rec.message)
        inv3 = plain(dispatch(self.world, "inv").message)
        self.assertIn("Spare Token", inv3)

        lost2 = plain(dispatch(self.world, "lost").message)
        self.assertNotIn("Spare Token", lost2)

    def test_lose_alias_and_undo(self) -> None:
        dispatch(self.world, "lose spare")
        self.assertNotIn(
            "Spare Token", plain(dispatch(self.world, "inv").message)
        )
        u = dispatch(self.world, "undo")
        self.assertTrue(u.ok, msg=u.message)
        self.assertIn(
            "Spare Token", plain(dispatch(self.world, "inv").message)
        )

    def test_cannot_despawn_player_or_place(self) -> None:
        r = dispatch(self.world, "despawn builder")
        # may not resolve or refuse
        self.assertTrue(
            "Cannot" in plain(r.message) or "No" in plain(r.message),
            msg=r.message,
        )


if __name__ == "__main__":
    unittest.main()
