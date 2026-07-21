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
        # may not resolve or refuse (player / not person path)
        self.assertTrue(
            "Cannot" in plain(r.message)
            or "No" in plain(r.message)
            or "operator" in plain(r.message).lower(),
            msg=r.message,
        )

    def test_person_despawn_to_off_duty(self) -> None:
        self.assertTrue(
            dispatch(
                self.world,
                "create person Temp Hire | Contractor for a day.",
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn temp-hire").ok)
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Temp Hire", look)

        r = dispatch(self.world, "despawn Temp Hire")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Off Duty", text)
        look2 = plain(dispatch(self.world, "look").message)
        self.assertNotIn("Temp Hire", look2)

        od = plain(dispatch(self.world, "off-duty").message)
        self.assertIn("Off Duty", od)
        self.assertIn("Temp Hire", od)
        # Not in Lost Dept
        lost = plain(dispatch(self.world, "lost").message)
        self.assertNotIn("Temp Hire", lost)

        back = dispatch(self.world, "onduty Temp Hire")
        self.assertTrue(back.ok, msg=back.message)
        self.assertIn("On duty", plain(back.message))
        look3 = plain(dispatch(self.world, "look").message)
        self.assertIn("Temp Hire", look3)

        # clockout alias
        self.assertTrue(dispatch(self.world, "clockout Temp Hire").ok)
        self.assertIn(
            "Temp Hire", plain(dispatch(self.world, "off-duty").message)
        )

    def test_dump_inventory(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create object Junk A | a").ok
        )
        self.assertTrue(dispatch(self.world, "spawn junk-a").ok)
        self.assertTrue(dispatch(self.world, "take junk a").ok)
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Spare Token", inv)
        self.assertIn("Junk A", inv)

        r = dispatch(self.world, "dump inv")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Dumped", text)
        inv2 = plain(dispatch(self.world, "inv").message)
        self.assertNotIn("Spare Token", inv2)
        self.assertNotIn("Junk A", inv2)
        lost = plain(dispatch(self.world, "lost").message)
        self.assertIn("Spare Token", lost)
        self.assertIn("Junk A", lost)

        u = dispatch(self.world, "undo")
        self.assertTrue(u.ok, msg=u.message)
        inv3 = plain(dispatch(self.world, "inv").message)
        self.assertIn("Spare Token", inv3)
        self.assertIn("Junk A", inv3)

    def test_dump_from_bin_shallow(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create bin Outer | outer bin").ok
        )
        self.assertTrue(dispatch(self.world, "spawn outer").ok)
        self.assertTrue(dispatch(self.world, "take outer").ok)
        self.assertTrue(
            dispatch(self.world, "create object Coin | shiny").ok
        )
        self.assertTrue(dispatch(self.world, "spawn coin").ok)
        self.assertTrue(dispatch(self.world, "put coin in outer").ok)

        r = dispatch(self.world, "dump from outer")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Dumped", plain(r.message))
        # Coin gone from bin → Lost Dept; outer still carried
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Outer", inv)
        lost = plain(dispatch(self.world, "lost").message)
        self.assertIn("Coin", lost)

        r2 = dispatch(self.world, "despawn all from outer")
        self.assertTrue(r2.ok, msg=r2.message)
        # empty bin message
        self.assertIn("empty", plain(r2.message).lower())


class NukePrimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_nuke_requires_confirmed(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create thing Nuke Target | disposable").ok
        )
        self.assertTrue(dispatch(self.world, "spawn nuke-target").ok)
        r = dispatch(self.world, "nuke Nuke Target")
        text = plain(r.message)
        self.assertIn("NUKE ARMED", text)
        self.assertIn("confirmed", text.lower())
        # Still exists
        self.assertIsNotNone(self.world.find_ven("Nuke Target"))

    def test_nuke_prime_with_confirmed(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create thing Doomed Widget | bye").ok
        )
        self.assertTrue(dispatch(self.world, "spawn doomed-widget").ok)
        self.assertTrue(dispatch(self.world, "spawn doomed-widget as Copy Two").ok)
        r = dispatch(self.world, "nuke doomed-widget confirmed")
        text = plain(r.message)
        self.assertIn("Nuked", text)
        self.assertIn("2", text)  # two instances
        self.assertIsNone(self.world.find_ven("Doomed Widget"))
        look = plain(dispatch(self.world, "look").message)
        self.assertNotIn("Doomed Widget", look)
        self.assertNotIn("Copy Two", look)

    def test_nuke_blocked_for_player(self) -> None:
        # story seed player is present
        pid = self.world.player_id()
        assert pid
        player = self.world.get_instance(pid)
        assert player is not None
        r = dispatch(self.world, f"nuke {player.ven_slug} confirmed")
        text = plain(r.message).lower()
        self.assertTrue(
            "cannot" in text or "player" in text,
            msg=r.message,
        )


if __name__ == "__main__":
    unittest.main()


