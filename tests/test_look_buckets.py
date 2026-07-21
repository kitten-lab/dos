"""Look / examine placement buckets: Here + named containers (not kind taxonomy)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.seed import seed_world_void
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_void(conn)
    return World(conn)


class LookPlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_look_at_in_on_route_to_examine(self) -> None:
        """look at/in/on <thing> peels English glue into examine."""
        self.assertTrue(
            dispatch(self.world, "create bin Drawer | Sliding.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn drawer").ok)
        self.assertTrue(
            dispatch(self.world, "create thing Brass Door | Portal plate.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn brass-door").ok)
        self.assertTrue(
            dispatch(self.world, "create thing Coin | Dull.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn coin").ok)
        self.assertTrue(dispatch(self.world, "put coin in drawer").ok)

        at = plain(dispatch(self.world, "look at brass-door").message)
        self.assertIn("Brass Door", at)
        # examine chrome, not room paths block alone
        self.assertTrue(
            "door" in at.lower() or "thing" in at.lower() or "brass" in at.lower(),
            msg=at,
        )

        into = plain(dispatch(self.world, "look in drawer").message)
        self.assertIn("Drawer", into)
        self.assertIn("Coin", into)

        on = plain(dispatch(self.world, "look on the drawer").message)
        self.assertIn("Drawer", on)
        self.assertIn("Coin", on)

        bare = plain(dispatch(self.world, "look drawer").message)
        self.assertIn("Drawer", bare)

        deep = plain(dispatch(self.world, "look --deep in drawer").message)
        self.assertIn("Drawer", deep)

    def test_room_loose_items_under_here_not_type_buckets(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create event The Knock | Three soft taps.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn the-knock").ok)
        self.assertTrue(
            dispatch(
                self.world, "create archetype The Watcher | Eyes in the grain."
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn the-watcher").ok)
        self.assertTrue(
            dispatch(self.world, "create feeling Distant Hum | Pressure.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn distant-hum").ok)

        text = plain(dispatch(self.world, "look").message)
        # No kind taxonomy sections
        self.assertNotIn("Happened Here", text)
        self.assertNotIn("Force", text)
        self.assertNotIn("Also present", text)
        self.assertNotIn("Things", text)
        # All loose presence under Here
        self.assertIn("Here", text)
        self.assertIn("The Knock", text)
        self.assertIn("The Watcher", text)
        self.assertIn("Distant Hum", text)

    def test_container_bucket_shallow_kids_and_empty(self) -> None:
        self.assertTrue(dispatch(self.world, "create bin Table | Oak.").ok)
        self.assertTrue(dispatch(self.world, "spawn table").ok)
        self.assertTrue(
            dispatch(self.world, "create box Drawer | Sliding.").ok
        )  # box → bin alias
        self.assertTrue(dispatch(self.world, "spawn drawer").ok)
        self.assertTrue(
            dispatch(self.world, "create container Empty Shelf | Bare.").ok
        )  # container → bin alias
        self.assertTrue(dispatch(self.world, "spawn empty-shelf").ok)
        self.assertTrue(
            dispatch(self.world, "create object Coffee | Warm.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn coffee").ok)
        self.assertTrue(
            dispatch(self.world, "create object Pink Button | Cute.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn pink-button").ok)

        self.assertTrue(dispatch(self.world, "put drawer in table").ok)
        self.assertTrue(dispatch(self.world, "put coffee in table").ok)
        self.assertTrue(dispatch(self.world, "put pink-button in drawer").ok)

        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Table", look)
        self.assertIn("Empty Shelf", look)
        self.assertIn("(empty)", look)
        # Container header: lived name + light prime (even if same) + subtype if any
        self.assertRegex(look, r"Table\s+·\s+Table")
        # Shallow under Table: Drawer + Coffee, not Pink Button
        self.assertIn("Drawer", look)
        self.assertIn("Coffee", look)
        self.assertNotIn("Pink Button", look)
        # Button is not loose on the floor
        # (void seed may have a book under Here — button must not be there alone as floor item)
        # Pink Button only appears when examining drawer/table open path

        ex_table = plain(dispatch(self.world, "examine table").message)
        self.assertIn("Here", ex_table)
        self.assertIn("Coffee", ex_table)
        self.assertIn("Drawer", ex_table)
        # Nested container opened one level
        self.assertIn("Pink Button", ex_table)

        ex_drawer = plain(dispatch(self.world, "examine drawer").message)
        self.assertIn("Pink Button", ex_drawer)
        self.assertNotIn("Coffee", ex_drawer)

        # look --deep: nested bin header + kids (not Drawer as a plain list row)
        look_deep = plain(dispatch(self.world, "look --deep").message)
        self.assertIn("Pink Button", look_deep)
        self.assertIn("└─", look_deep)
        deep_lines = look_deep.splitlines()
        drawer_hdr = next(
            (ln for ln in deep_lines if "└─" in ln and "Drawer" in ln),
            "",
        )
        self.assertTrue(drawer_hdr, msg=look_deep)
        # Face code on nested bin header (office slug-hex, not legacy BIN-001)
        self.assertRegex(drawer_hdr, r"[a-z0-9]{2,4}-[0-9a-f]{6}")
        # Loose root (Coffee) before nested bins, with blank line + Here label
        coffee_i = next(
            i for i, ln in enumerate(deep_lines) if "Coffee" in ln
        )
        drawer_i = next(
            i for i, ln in enumerate(deep_lines) if "└─" in ln and "Drawer" in ln
        )
        self.assertLess(coffee_i, drawer_i, msg=look_deep)
        # blank line between root block and first nested bin
        between = deep_lines[coffee_i + 1 : drawer_i]
        self.assertTrue(
            any(not ln.strip() for ln in between) or any("Here" in ln for ln in deep_lines[coffee_i - 2 : coffee_i + 1]),
            msg=look_deep,
        )
        # shallow look still hides button
        look_shallow = plain(dispatch(self.world, "look").message)
        self.assertNotIn("Pink Button", look_shallow)
        self.assertNotIn("└─", look_shallow)

        # Nested box under drawer: deep examine of table opens drawer kids;
        # deep also expands Drawer-as-row... wait, examine table has Drawer as section
        # with Pink Button. Add inner bin for examine --deep expansion.
        self.assertTrue(
            dispatch(self.world, "create bin Nest | tiny").ok
        )
        self.assertTrue(dispatch(self.world, "spawn nest").ok)
        self.assertTrue(
            dispatch(self.world, "create thing Coin | shiny").ok
        )
        self.assertTrue(dispatch(self.world, "spawn coin").ok)
        self.assertTrue(dispatch(self.world, "put nest in drawer").ok)
        self.assertTrue(dispatch(self.world, "put coin in nest").ok)
        # examine table: Drawer section lists Nest + Pink Button (not Coin)
        ex_t = plain(dispatch(self.world, "examine table").message)
        self.assertIn("Nest", ex_t)
        self.assertNotIn("Coin", ex_t)
        # examine --deep table: Nest expands one layer → Coin
        ex_td = plain(dispatch(self.world, "examine --deep table").message)
        self.assertIn("Coin", ex_td)
        self.assertIn("Nest", ex_td)

    def test_presence_columns_are_name_subtype_prime_code(self) -> None:
        """Look/examine rows: lived name · subtype · origin VEN · face code."""
        self.assertTrue(
            dispatch(
                self.world,
                "create feeling/longing Soft Ache | A quieter cousin.",
            ).ok
        )
        self.assertTrue(dispatch(self.world, "spawn soft-ache").ok)
        text = plain(dispatch(self.world, "look").message)
        ache = next(
            ln for ln in text.splitlines() if "Soft Ache" in ln or "Ache" in ln
        )
        # Subtype alone as col2 — not kind/subtype mash
        self.assertNotIn("feeling/longing", ache)
        self.assertNotRegex(ache, r"\blonging\s+sense\b")
        self.assertIn("longing", ache)
        self.assertLess(ache.index("Soft Ache"), ache.index("longing"))
        # Office face code (slug3-hex), not legacy SNS-001-0001
        self.assertRegex(ache, r"[a-z0-9]{2,4}-[0-9a-f]{6}")
        # Lived name appears before origin prime when they differ
        self.assertTrue(
            dispatch(self.world, "create sense Bare Hum | x.").ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn bare-hum as Loud Hum").ok
        )
        text2 = plain(dispatch(self.world, "look").message)
        bare = next(ln for ln in text2.splitlines() if "Loud Hum" in ln)
        self.assertRegex(bare, r"Loud Hum")
        self.assertRegex(bare, r"Bare Hum")
        # name first: Loud Hum before Bare Hum on the row
        self.assertLess(bare.index("Loud Hum"), bare.index("Bare Hum"))
        self.assertRegex(bare, r"[a-z0-9]{2,4}-[0-9a-f]{6}")

    def test_bin_bucket_header_subtype_before_prime(self) -> None:
        """Bin section title: name · subtype · prime · code (subtype is col2)."""
        self.assertTrue(
            dispatch(
                self.world,
                "create bin/drawer Filing | Sliding oak drawer.",
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn filing as Active Drawer").ok
        )
        look = plain(dispatch(self.world, "look").message)
        # Header line (section title), not a content row
        hdr = next(
            ln
            for ln in look.splitlines()
            if "Active Drawer" in ln and "·" in ln
        )
        self.assertIn("drawer", hdr)
        self.assertIn("Filing", hdr)
        # col order after name: subtype before root VEN name
        self.assertLess(hdr.index("drawer"), hdr.index("Filing"))
        # office face code still present
        self.assertRegex(hdr, r"[a-z0-9]{2,4}-[0-9a-f]{6}")

    def test_deep_item_row_subtype_before_prime(self) -> None:
        """look --deep leaf rows: name · subtype · prime · code."""
        self.assertTrue(
            dispatch(self.world, "create bin Table | Oak.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn table").ok)
        self.assertTrue(
            dispatch(self.world, "create bin Nest | Inner.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn nest").ok)
        self.assertTrue(
            dispatch(
                self.world,
                "create thing/key Brass Key | Opens nothing important.",
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn brass-key as Spare Key").ok
        )
        self.assertTrue(dispatch(self.world, "put nest in table").ok)
        self.assertTrue(dispatch(self.world, "put spare key in nest").ok)

        deep = plain(dispatch(self.world, "look --deep").message)
        # Nested bin header under Table
        self.assertIn("Nest", deep)
        # Leaf item row under Nest
        key_ln = next(ln for ln in deep.splitlines() if "Spare Key" in ln)
        self.assertIn("key", key_ln)
        self.assertIn("Brass Key", key_ln)
        # name · subtype · prime
        self.assertLess(key_ln.index("Spare Key"), key_ln.index("key"))
        self.assertLess(key_ln.index("key"), key_ln.index("Brass Key"))
        self.assertRegex(key_ln, r"[a-z0-9]{2,4}-[0-9a-f]{6}")


class EventKindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_event_is_root_with_subtype(self) -> None:
        from dos.world import parse_kind_spec, KINDS

        self.assertIn("event", KINDS)
        self.assertEqual(parse_kind_spec("event"), ("event", None))
        self.assertEqual(parse_kind_spec("event/meeting"), ("event", "meeting"))
        r = dispatch(
            self.world,
            "create event/meeting Soft Kickoff | The room holds the beat.",
        )
        self.assertTrue(r.ok, msg=r.message)
        msg = plain(r.message).lower()
        self.assertIn("event", msg)
        self.assertIn("meeting", msg)
        self.assertNotIn("sense/event", msg)
        ven = self.world.find_ven("Soft Kickoff")
        assert ven is not None
        self.assertEqual(ven.kind, "event")
        self.assertEqual((ven.subtype or "").lower(), "meeting")
        from dos.ids import is_office_ven_code

        self.assertTrue(
            ven.code and is_office_ven_code(ven.code), msg=ven.code
        )
        self.assertTrue(dispatch(self.world, "spawn soft-kickoff").ok)
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Soft Kickoff", look)
        kick = next(ln for ln in look.splitlines() if "Kickoff" in ln)
        self.assertRegex(kick, r"[a-z0-9]{2,4}-[0-9a-f]{6}")


class DigBinAndTakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_dig_bin_lands_here_takeable_and_put_into(self) -> None:
        """dig bin X must create a floor bin (not a free-floating place)."""
        r = dispatch(self.world, "dig bin Table | Oak.")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("here", plain(r.message).lower())
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Table", look)
        take = dispatch(self.world, "take table")
        self.assertTrue(take.ok, msg=take.message)
        self.assertIn("Taken", plain(take.message))
        drop = dispatch(self.world, "drop table")
        self.assertTrue(drop.ok, msg=drop.message)
        self.assertTrue(dispatch(self.world, "create thing Coin | shiny").ok)
        self.assertTrue(dispatch(self.world, "spawn coin").ok)
        put = dispatch(self.world, "put coin in table")
        self.assertTrue(put.ok, msg=put.message)
        self.assertIn("Put", plain(put.message))

    def test_create_spawn_bin_takeable(self) -> None:
        self.assertTrue(dispatch(self.world, "create bin Shelf | s").ok)
        self.assertTrue(dispatch(self.world, "spawn shelf").ok)
        r = dispatch(self.world, "take shelf")
        self.assertTrue(r.ok, msg=r.message)


if __name__ == "__main__":
    unittest.main()
