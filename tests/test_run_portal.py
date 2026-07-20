"""Installed apps: portal bind + run into real places (not room exits)."""

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


class RunPortalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        # Device + app + world
        self.assertTrue(
            dispatch(self.world, "create object Terminal IO | Humming beige.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn terminal-io").ok)
        self.assertTrue(
            dispatch(self.world, "create object/app Mail | Never sleeps.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn mail").ok)
        dig = dispatch(self.world, "dig place/app Mailroom")
        self.assertTrue(dig.ok, dig.message)
        self.assertIn("place/app", plain(dig.message))

    def test_not_installed_on_floor(self) -> None:
        # Apps on the floor must NOT run — only door shells are floor portals.
        self.assertTrue(dispatch(self.world, "portal mail -> Mailroom").ok)
        r = dispatch(self.world, "run mail")
        self.assertFalse(r.ok)
        self.assertIn("not installed", plain(r.message).lower())

    def test_run_from_device(self) -> None:
        self.assertTrue(dispatch(self.world, "portal mail -> Mailroom").ok)
        self.assertTrue(dispatch(self.world, "put mail in terminal").ok)
        # Not on exits
        exits = plain(dispatch(self.world, "exits").message).lower()
        self.assertNotIn("mail", exits)
        self.assertNotIn("mailroom", exits)

        r = dispatch(self.world, "run mail from terminal")
        self.assertTrue(r.ok, r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Mailroom", loc.name)
        self.assertEqual(loc.ven_subtype, "app")
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Mailroom", look)
        # Look location: subtype only (no root "place" kind)
        self.assertRegex(look, r"\bapp\b")
        self.assertNotRegex(look, r"place\s*:\s*app")

    def test_soft_run_unique_installed(self) -> None:
        self.assertTrue(dispatch(self.world, "portal mail -> Mailroom").ok)
        self.assertTrue(dispatch(self.world, "put mail in terminal").ok)
        r = dispatch(self.world, "run mail")
        self.assertTrue(r.ok, r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Mailroom", loc.name)

    def test_no_portal_bound(self) -> None:
        self.assertTrue(dispatch(self.world, "put mail in terminal").ok)
        r = dispatch(self.world, "run mail from terminal")
        self.assertFalse(r.ok)
        self.assertIn("portal", plain(r.message).lower())

    def test_examine_device_marks_runnable(self) -> None:
        self.assertTrue(dispatch(self.world, "portal mail -> Mailroom").ok)
        self.assertTrue(dispatch(self.world, "put mail in terminal").ok)
        ex = plain(dispatch(self.world, "examine terminal").message)
        self.assertIn("Mail", ex)
        self.assertIn("run", ex.lower())

    def test_storybook_place_and_game_object(self) -> None:
        self.assertTrue(
            dispatch(
                self.world,
                "create object/game Kat Moire: Kitten Detective | Soft paws.",
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn kat-moire").ok)
        dig = dispatch(
            self.world, "dig place/storybook City of Soft Alibis"
        )
        self.assertTrue(dig.ok, dig.message)
        self.assertTrue(
            dispatch(
                self.world, "portal kat-moire -> City of Soft Alibis"
            ).ok
        )
        self.assertTrue(dispatch(self.world, "put kat-moire in terminal").ok)
        r = dispatch(self.world, "run kat from terminal")
        self.assertTrue(r.ok, r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Soft Alibis", loc.name)
        self.assertEqual(loc.ven_subtype, "storybook")

    def test_portal_clear_and_undo(self) -> None:
        self.assertTrue(dispatch(self.world, "portal mail -> Mailroom").ok)
        mail = self.world.resolve_here_named("mail")
        assert mail is not None
        self.assertIsNotNone(self.world.get_portal_to(mail.id))
        self.assertTrue(dispatch(self.world, "portal clear mail").ok)
        self.assertIsNone(self.world.get_portal_to(mail.id))
        self.assertTrue(dispatch(self.world, "undo").ok)
        self.assertIsNotNone(self.world.get_portal_to(mail.id))

    def test_portal_survives_take_and_reinstall(self) -> None:
        """Binding is on the app; take/put never require re-portal."""
        self.assertTrue(dispatch(self.world, "portal mail -> Mailroom").ok)
        self.assertTrue(dispatch(self.world, "put mail in terminal").ok)
        mail = None
        term = self.world.resolve_here_named("terminal")
        assert term is not None
        for c in self.world.contents(term.id):
            if "mail" in c.name.lower():
                mail = c
                break
        assert mail is not None
        dest_id = self.world.get_portal_to(mail.id)
        self.assertIsNotNone(dest_id)

        take = dispatch(self.world, "take mail from terminal")
        self.assertTrue(take.ok, take.message)
        self.assertIn("portal still", plain(take.message).lower())
        mail2 = self.world.resolve_here_named("mail")
        assert mail2 is not None
        self.assertEqual(self.world.get_portal_to(mail2.id), dest_id)
        # Loose in inventory (not floor, not installed) → run fails; link intact
        r_loose = dispatch(self.world, "run mail")
        self.assertFalse(r_loose.ok)
        msg = plain(r_loose.message).lower()
        self.assertTrue(
            "not installed" in msg or "not on the floor" in msg or "device" in msg,
            msg=r_loose.message,
        )

        put = dispatch(self.world, "install mail in terminal")
        self.assertTrue(put.ok, put.message)
        self.assertIn("binding kept", plain(put.message).lower())
        r = dispatch(self.world, "run mail")
        self.assertTrue(r.ok, r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Mailroom", loc.name)

    def test_logout_returns_to_entry_not_link(self) -> None:
        origin = self.world.player_location()
        assert origin is not None
        origin_id = origin.id
        self.assertTrue(dispatch(self.world, "portal mail -> Mailroom").ok)
        self.assertTrue(dispatch(self.world, "put mail in terminal").ok)
        self.assertTrue(dispatch(self.world, "run mail from terminal").ok)
        # Dig deeper inside the app world and walk there — logout still returns
        self.assertTrue(dispatch(self.world, "dig Inner Inbox").ok)
        self.assertTrue(
            dispatch(self.world, "link deeper -> Inner Inbox").ok
        )
        self.assertTrue(dispatch(self.world, "go deeper").ok)
        inner = self.world.player_location()
        assert inner is not None
        self.assertIn("Inner", inner.name)

        r = dispatch(self.world, "logout")
        self.assertTrue(r.ok, r.message)
        self.assertIn("logout", plain(r.message).lower())
        back = self.world.player_location()
        assert back is not None
        self.assertEqual(back.id, origin_id)
        self.assertIsNone(self.world.peek_portal_session())

    def test_logout_when_not_in_session(self) -> None:
        r = dispatch(self.world, "logout")
        self.assertTrue(r.ok)
        self.assertIn("nothing", plain(r.message).lower())

    def test_unlock_floor_door_portal(self) -> None:
        """Room-as-portal: token on floor, open/enter without device install."""
        dig = dispatch(self.world, "dig place/room Soft Suite | Soft lamp.")
        self.assertTrue(dig.ok, dig.message)
        self.assertTrue(
            dispatch(
                self.world, "create thing/door Brass Door | Plate waits."
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn brass-door").ok)
        self.assertTrue(
            dispatch(self.world, "portal brass-door -> Soft Suite").ok
        )
        door = self.world.resolve_here_named("brass")
        assert door is not None
        self.assertIsNotNone(self.world.get_portal_to(door.id))
        exits = plain(dispatch(self.world, "exits").message).lower()
        self.assertNotIn("soft suite", exits)

        r = dispatch(self.world, "open brass-door")
        self.assertTrue(r.ok, r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Soft Suite", loc.name)
        self.assertEqual(loc.ven_subtype, "room")

        origin_back = dispatch(self.world, "logout")
        self.assertTrue(origin_back.ok, origin_back.message)

        r2 = dispatch(self.world, "enter brass")
        self.assertTrue(r2.ok, r2.message)

    def test_lock_deny_line_on_open(self) -> None:
        """lock -d sets flavor printed when open fails while locked."""
        dig = dispatch(self.world, "dig place/room Soft Suite | Soft lamp.")
        self.assertTrue(dig.ok, dig.message)
        self.assertTrue(
            dispatch(
                self.world, "create thing/door Brass Door | Plate waits."
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world, "create thing/key Brass Key | Cold teeth."
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn brass-door").ok)
        self.assertTrue(dispatch(self.world, "spawn brass-key").ok)
        self.assertTrue(
            dispatch(self.world, "portal brass-door -> Soft Suite").ok
        )
        r = dispatch(
            self.world,
            'lock brass-door with brass-key -d "The latch laughs at bare hands."',
        )
        self.assertTrue(r.ok, r.message)
        door = self.world.resolve_here_named("brass-door")
        assert door is not None
        self.assertIn("laughs", (self.world.get_portal_lock_deny(door.id) or ""))

        blocked = dispatch(self.world, "open brass-door")
        self.assertFalse(blocked.ok)
        text = plain(blocked.message)
        self.assertIn("latch laughs", text.lower())
        self.assertIn("locked", text.lower())

        # Clear deny with empty -d
        self.assertTrue(
            dispatch(self.world, 'lock brass-door -d ""').ok
        )
        self.assertIsNone(self.world.get_portal_lock_deny(door.id))
        blocked2 = dispatch(self.world, "open brass-door")
        self.assertFalse(blocked2.ok)
        self.assertNotIn("latch laughs", plain(blocked2.message).lower())

    def test_lock_key_unlock_open(self) -> None:
        """lock with key → open fails → unlock with key → open works."""
        dig = dispatch(self.world, "dig place/room Soft Suite | Soft lamp.")
        self.assertTrue(dig.ok, dig.message)
        self.assertTrue(
            dispatch(
                self.world, "create thing/door Brass Door | Plate waits."
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world, "create thing/key Brass Key | Cold teeth."
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn brass-door").ok)
        self.assertTrue(dispatch(self.world, "spawn brass-key").ok)
        self.assertTrue(
            dispatch(self.world, "portal brass-door -> Soft Suite").ok
        )
        self.assertTrue(
            dispatch(self.world, "lock brass-door with brass-key").ok
        )
        door = self.world.resolve_here_named("brass-door")
        assert door is not None
        self.assertTrue(self.world.is_portal_locked(door.id))

        blocked = dispatch(self.world, "open brass-door")
        self.assertFalse(blocked.ok)
        self.assertIn("locked", plain(blocked.message).lower())

        # Wrong key
        self.assertTrue(
            dispatch(
                self.world, "create thing/key Iron Key | Wrong teeth."
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn iron-key").ok)
        bad = dispatch(self.world, "unlock brass-door with iron-key")
        self.assertFalse(bad.ok)

        good = dispatch(self.world, "unlock brass-door with brass-key")
        self.assertTrue(good.ok, good.message)
        self.assertIn("unlocked", plain(good.message).lower())
        self.assertFalse(self.world.is_portal_locked(door.id))

        # Still here until open
        loc0 = self.world.player_location()
        assert loc0 is not None
        self.assertNotIn("Soft Suite", loc0.name)

        entered = dispatch(self.world, "open brass-door")
        self.assertTrue(entered.ok, entered.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Soft Suite", loc.name)

        # Auto key from inventory after re-lock *with the same key copy*
        dispatch(self.world, "logout")
        self.assertTrue(
            dispatch(self.world, "lock brass-door with brass-key").ok
        )
        self.assertTrue(dispatch(self.world, "take brass-key").ok)
        auto = dispatch(self.world, "unlock brass-door")
        self.assertTrue(auto.ok, auto.message)
        self.assertTrue(dispatch(self.world, "enter brass-door").ok)

    def test_one_prime_key_named_spawns_are_distinct(self) -> None:
        """Prime Key + Cellar/Suite instances — only the bound copy opens the door."""
        dig = dispatch(self.world, "dig place/room Soft Suite | Soft lamp.")
        self.assertTrue(dig.ok, dig.message)
        self.assertTrue(
            dispatch(self.world, "create thing/door Brass Door | Plate.").ok
        )
        self.assertTrue(
            dispatch(self.world, "create thing/key Key | Blank teeth.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn brass-door").ok)
        self.assertTrue(dispatch(self.world, "spawn key as Cellar Key").ok)
        self.assertTrue(dispatch(self.world, "spawn key as Suite Key").ok)
        self.assertTrue(
            dispatch(self.world, "portal brass-door -> Soft Suite").ok
        )
        self.assertTrue(
            dispatch(self.world, "lock brass-door with cellar-key").ok
        )
        door = self.world.resolve_here_named("brass-door")
        cellar = self.world.resolve_here_named("cellar")
        suite = self.world.resolve_here_named("suite")
        assert door and cellar and suite
        self.assertEqual(
            self.world.get_portal_key_instance_id(door.id), cellar.id
        )
        self.assertEqual(cellar.ven_id, suite.ven_id)

        bad = dispatch(self.world, "unlock brass-door with suite-key")
        self.assertFalse(bad.ok, msg=bad.message)
        self.assertTrue(
            "not the key" in plain(bad.message).lower()
            or "does not fit" in plain(bad.message).lower()
            or "need" in plain(bad.message).lower(),
            msg=bad.message,
        )

        good = dispatch(self.world, "unlock brass-door with cellar-key")
        self.assertTrue(good.ok, good.message)
        self.assertTrue(dispatch(self.world, "open brass-door").ok)

    def test_app_only_runs_when_in_box(self) -> None:
        """Pillow-box pattern: game/app on floor fails; install in bin works."""
        dig = dispatch(self.world, "dig place/app Skalitz | Mud.")
        self.assertTrue(dig.ok, dig.message)
        self.assertTrue(
            dispatch(
                self.world, "create thing/game KCD | Henry's trouble."
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn kcd").ok)
        self.assertTrue(dispatch(self.world, "portal kcd -> Skalitz").ok)
        self.assertTrue(
            dispatch(self.world, "create bin Pillow Box | Soft hide.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn pillow-box").ok)

        floor = dispatch(self.world, "run kcd")
        self.assertFalse(floor.ok)
        self.assertIn("not installed", plain(floor.message).lower())

        self.assertTrue(dispatch(self.world, "put kcd in pillow-box").ok)
        r = dispatch(self.world, "run kcd")
        self.assertTrue(r.ok, r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertIn("Skalitz", loc.name)
        dispatch(self.world, "logout")

    def test_open_folio_still_works_when_no_portal(self) -> None:
        """open prefers portal; falls through to folio when unbound."""
        self.assertTrue(
            dispatch(
                self.world, "create book Field Notes | Pocket ruled."
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn field-notes").ok)
        self.assertTrue(
            dispatch(
                self.world, "folio page add field-notes Leaf One | hello"
            ).ok
        )
        r = dispatch(self.world, "open field-notes")
        self.assertTrue(r.ok, r.message)
        text = plain(r.message).lower()
        self.assertTrue(
            "leaf" in text or "page" in text or "field" in text,
            msg=r.message,
        )


if __name__ == "__main__":
    unittest.main()
