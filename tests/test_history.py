"""Story-when history: timeline nodes + life-of-item entries."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.story_when import (
    format_history_line,
    normalize_story_when,
    peel_story_when_suffix,
    peel_when_anywhere,
)
from dos.seed import seed_world_bootstrap
from dos.world import World


class StoryWhenParseTests(unittest.TestCase):
    def test_peel_suffix(self) -> None:
        rest, sw, n = peel_story_when_suffix("quill as Pocket when @3")
        self.assertEqual(rest, "quill as Pocket")
        self.assertEqual(sw, "@3")
        self.assertEqual(n, 3)
        rest, sw, n = peel_story_when_suffix("thing X | soft. when @unknown")
        self.assertTrue(rest.endswith("soft."))
        self.assertEqual(sw, "@unknown")
        self.assertIsNone(n)

    def test_peel_when_anywhere(self) -> None:
        rest, sw, n = peel_when_anywhere("hope in cartographer when @1")
        self.assertEqual(rest, "hope in cartographer")
        self.assertEqual(sw, "@1")
        self.assertEqual(n, 1)
        rest, sw, n = peel_when_anywhere("silver from box --when 0")
        self.assertEqual(rest, "silver from box")
        self.assertEqual(sw, "@0")
        self.assertEqual(n, 0)
        rest, sw, n = peel_when_anywhere("silver --when 2 from box")
        self.assertEqual(rest, "silver from box")
        self.assertEqual(sw, "@2")
        self.assertEqual(n, 2)
        rest, sw, n = peel_when_anywhere("just silver")
        self.assertEqual(rest, "just silver")
        self.assertEqual(sw, "@unknown")
        self.assertIsNone(n)

    def test_normalize(self) -> None:
        self.assertEqual(normalize_story_when("@0"), ("@0", 0))
        self.assertEqual(normalize_story_when("@unknown"), ("@unknown", None))
        self.assertEqual(normalize_story_when("Cow Jump"), ("@unknown", None))

    def test_format_history_two_lines(self) -> None:
        block = format_history_line(
            verb="put",
            story_when="@3",
            crafted_at="2026-07-16 12:00:00",
            place_name="Herenow",
            realm_name="Base",
            timeline_name="Start",
            note="into Keeper [interior]",
            event_code="HST-004",
        )
        primary, meta = block.split("\n", 1)
        self.assertEqual(
            primary, "HST-004  ·  put  ·  into Keeper [interior]"
        )
        self.assertIn("story @3", meta)
        self.assertIn("Herenow", meta)
        self.assertIn("Base / Start", meta)
        self.assertIn("craft 2026-07-16", meta)
        self.assertNotIn("put", meta)  # event stays on line 1


class HistoryCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        self.conn = connect(Path(tmp.name))
        seed_world_bootstrap(self.conn)
        self.world = World(self.conn)

    def test_create_and_spawn_record_story_when(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        place_title = loc.name

        r = dispatch(
            self.world,
            "create thing Story Quill | Soft graphite. when @0",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("@0", plain(r.message))
        ven = self.world.find_ven("Story Quill")
        assert ven is not None
        rows = self.world.history_for("ven", ven.id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["story_when"], "@0")
        self.assertEqual(rows[0]["verb"], "create")
        self.assertEqual(rows[0]["node_index"], 0)
        self.assertEqual(rows[0]["place_instance_id"], loc.id)
        self.assertEqual(rows[0]["place_name"], place_title)
        self.assertTrue((rows[0]["realm_name"] or "").strip())
        self.assertTrue((rows[0]["timeline_name"] or "").strip())

        r2 = dispatch(
            self.world, "spawn story-quill as Pocket Quill when @2"
        )
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertIn("@2", plain(r2.message))
        insts = self.world.list_instances_of_ven(ven.id)
        self.assertEqual(len(insts), 1)
        h = self.world.history_for("instance", insts[0].id)
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["story_when"], "@2")
        self.assertEqual(h[0]["node_index"], 2)
        self.assertEqual(h[0]["place_name"], place_title)
        self.assertEqual(h[0]["place_instance_id"], loc.id)

        nodes = plain(dispatch(self.world, "history nodes").message)
        self.assertIn("@0", nodes)
        self.assertIn("@2", nodes)

        listed = plain(dispatch(self.world, "history on pocket").message)
        self.assertIn("@2", listed)
        self.assertIn("spawn", listed.lower())
        self.assertIn(place_title, listed)

        ven_hist = plain(dispatch(self.world, "history ven Story Quill").message)
        self.assertIn("@0", ven_hist)
        self.assertIn("create", ven_hist.lower())
        self.assertIn(place_title, ven_hist)

    def test_omitted_when_is_unknown(self) -> None:
        r = dispatch(self.world, "create thing Bare Stick | wood.")
        self.assertTrue(r.ok, msg=r.message)
        ven = self.world.find_ven("Bare Stick")
        assert ven is not None
        rows = self.world.history_for("ven", ven.id)
        self.assertEqual(rows[0]["story_when"], "@unknown")
        self.assertIsNone(rows[0]["node_index"])

    def test_lore_when_at_node(self) -> None:
        r = dispatch(
            self.world, "lore add Founding | Raised for travelers. when @1"
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("@1", plain(r.message))
        loc = self.world.player_location()
        assert loc is not None
        # lore history is on lore id — find via nodes + any history with @1
        # place itself may have no instance history; check lore entry recorded
        # by scanning connection
        rows = self.conn.execute(
            "SELECT * FROM history_entries WHERE story_when = '@1' AND verb = 'lore'"
        ).fetchall()
        self.assertGreaterEqual(len(rows), 1)

    def test_take_drop_record_on_thing_place_and_player(self) -> None:
        self.assertTrue(
            dispatch(
                self.world, "create thing Move Coin | shiny. when @0"
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn move-coin as Coin when @0").ok
        )
        coin = self.world.resolve_here_named("Coin")
        assert coin is not None
        loc = self.world.player_location()
        player = self.world.get_instance(self.world.player_id() or "")
        assert loc is not None and player is not None

        spawn_rows = self.world.history_for("instance", coin.id)
        self.assertEqual(spawn_rows[0]["verb"], "spawn")
        spawn_code = spawn_rows[0]["event_code"]
        self.assertTrue(str(spawn_code).startswith("HST-"))
        # Floor spawn also lands on the place
        place_recv = [
            h
            for h in self.world.history_for("instance", loc.id)
            if h["verb"] == "receive" and h["event_code"] == spawn_code
        ]
        self.assertEqual(len(place_recv), 1)

        r = dispatch(self.world, "take coin --when 1")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("@1", plain(r.message))
        self.assertIn("HST-", plain(r.message))
        rows = self.world.history_for("instance", coin.id)
        take_row = next(row for row in rows if row["verb"] == "take")
        self.assertEqual(take_row["story_when"], "@1")
        code = take_row["event_code"]
        self.assertNotEqual(code, spawn_code)
        # Same event on place (give) and player (receive)
        self.assertTrue(
            any(
                h["event_code"] == code and h["verb"] == "give"
                for h in self.world.history_for("instance", loc.id)
            )
        )
        self.assertTrue(
            any(
                h["event_code"] == code and h["verb"] == "receive"
                for h in self.world.history_for("instance", player.id)
            )
        )
        me = plain(dispatch(self.world, "history me").message)
        self.assertIn(str(code), me)
        here = plain(dispatch(self.world, "history here").message)
        self.assertIn(str(code), here)

        r2 = dispatch(self.world, "drop coin")
        self.assertTrue(r2.ok, msg=r2.message)
        drop_row = next(
            row
            for row in self.world.history_for("instance", coin.id)
            if row["verb"] == "drop"
        )
        self.assertEqual(drop_row["story_when"], "@unknown")
        dcode = drop_row["event_code"]
        self.assertTrue(
            any(
                h["event_code"] == dcode and h["verb"] == "receive"
                for h in self.world.history_for("instance", loc.id)
            )
        )

    def test_put_shared_event_code_and_legs(self) -> None:
        self.assertTrue(
            dispatch(
                self.world, "create thing Hope Spark | faint light."
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn hope-spark as Hope").ok
        )
        self.assertTrue(
            dispatch(
                self.world, "create person Quiet Keeper | watches."
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn quiet-keeper as Keeper").ok
        )
        hope = self.world.resolve_here_named("Hope")
        keeper = self.world.resolve_here_named("Keeper")
        assert hope is not None and keeper is not None

        r = dispatch(self.world, "put hope in keeper when @3")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("@3", plain(r.message))

        hope_hist = self.world.history_for("instance", hope.id)
        put_rows = [h for h in hope_hist if h["verb"] == "put"]
        self.assertEqual(len(put_rows), 1)
        self.assertEqual(put_rows[0]["story_when"], "@3")
        code = put_rows[0]["event_code"]
        self.assertTrue(str(code).startswith("HST-"))
        self.assertIn(str(code), plain(r.message))

        keeper_hist = self.world.history_for("instance", keeper.id)
        recv = [h for h in keeper_hist if h["verb"] == "receive"]
        self.assertEqual(len(recv), 1)
        self.assertEqual(recv[0]["event_code"], code)
        self.assertEqual(recv[0]["story_when"], "@3")

        # Cross-lookup by event code shows both legs
        event_view = plain(dispatch(self.world, f"history {code}").message)
        self.assertIn("put", event_view.lower())
        self.assertIn("receive", event_view.lower())
        self.assertIn(str(code), event_view)

        listed = plain(dispatch(self.world, "history on hope").message)
        self.assertIn("put", listed.lower())
        self.assertIn("@3", listed)
        self.assertIn(str(code), listed)

        r2 = dispatch(self.world, "take hope from keeper --when 4")
        self.assertTrue(r2.ok, msg=r2.message)
        take_rows = [
            h
            for h in self.world.history_for("instance", hope.id)
            if h["verb"] == "take"
        ]
        self.assertTrue(any(h["story_when"] == "@4" for h in take_rows))
        tcode = next(h["event_code"] for h in take_rows if h["story_when"] == "@4")
        give_rows = [
            h
            for h in self.world.history_for("instance", keeper.id)
            if h["verb"] == "give" and h["event_code"] == tcode
        ]
        self.assertEqual(len(give_rows), 1)
        player = self.world.get_instance(self.world.player_id() or "")
        assert player is not None
        self.assertTrue(
            any(
                h["event_code"] == tcode and h["verb"] == "receive"
                for h in self.world.history_for("instance", player.id)
            )
        )

    def test_retime_updates_all_legs(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create thing Retime Coin | metal.").ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn retime-coin as Coin").ok
        )
        r = dispatch(self.world, "take coin")
        self.assertTrue(r.ok, msg=r.message)
        # Extract HST code from ok message
        msg = plain(r.message)
        import re

        m = re.search(r"HST-\d+", msg)
        self.assertIsNotNone(m, msg=msg)
        code = m.group(0)

        legs = self.world.history_for_event(code)
        self.assertGreaterEqual(len(legs), 2)
        for leg in legs:
            self.assertEqual(leg["story_when"], "@unknown")

        rt = dispatch(self.world, f"retime {code} when @5")
        self.assertTrue(rt.ok, msg=rt.message)
        self.assertIn("@5", plain(rt.message))
        legs2 = self.world.history_for_event(code)
        self.assertEqual(len(legs2), len(legs))
        for leg in legs2:
            self.assertEqual(leg["story_when"], "@5")
            self.assertEqual(leg["node_index"], 5)

        # Hash form + unknown clear
        rt2 = dispatch(self.world, f"retime #{code} @unknown")
        self.assertTrue(rt2.ok, msg=rt2.message)
        for leg in self.world.history_for_event(code):
            self.assertEqual(leg["story_when"], "@unknown")
            self.assertIsNone(leg["node_index"])

        # undo restores prior (the @5 stamps from before clear)
        self.assertTrue(dispatch(self.world, "undo").ok)
        for leg in self.world.history_for_event(code):
            self.assertEqual(leg["story_when"], "@5")
            self.assertEqual(leg["node_index"], 5)

        listed = plain(dispatch(self.world, f"history {code}").message)
        self.assertIn("@5", listed)

    def test_rename_records_on_instance(self) -> None:
        player = self.world.get_instance(self.world.player_id() or "")
        assert player is not None
        prior = player.name
        r = dispatch(self.world, "rename me as Danyi")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Danyi", plain(r.message))
        self.assertIn("HST-", plain(r.message))
        rows = self.world.history_for("instance", player.id)
        ren = [h for h in rows if h["verb"] == "rename"]
        self.assertEqual(len(ren), 1)
        self.assertEqual(ren[0]["story_when"], "@unknown")
        note = ren[0]["note"] or ""
        self.assertIn(prior, note)
        self.assertIn("Danyi", note)
        self.assertIn("→", note)
        me = plain(dispatch(self.world, "history me").message)
        self.assertIn("rename", me.lower())
        self.assertIn("Danyi", me)

        r2 = dispatch(self.world, "rename me as Ada when @2")
        self.assertTrue(r2.ok, msg=r2.message)
        ren2 = [
            h
            for h in self.world.history_for("instance", player.id)
            if h["verb"] == "rename" and h["story_when"] == "@2"
        ]
        self.assertEqual(len(ren2), 1)
        self.assertIn("Ada", ren2[0]["note"] or "")

    def test_put_into_player_logs_on_me(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create thing Pocket Stone | cool.").ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn pocket-stone as Stone").ok
        )
        player = self.world.get_instance(self.world.player_id() or "")
        assert player is not None
        r = dispatch(self.world, "put stone in me when @2")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Put", plain(r.message))
        me_hist = self.world.history_for("instance", player.id)
        recv = [h for h in me_hist if h["verb"] == "receive"]
        self.assertTrue(any(h["story_when"] == "@2" for h in recv))
        # Also by builder name
        self.assertTrue(
            dispatch(self.world, "drop stone").ok
        )
        r2 = dispatch(self.world, f"put stone in {player.name} --when 5")
        self.assertTrue(r2.ok, msg=r2.message)
        me2 = plain(dispatch(self.world, "history me").message)
        self.assertIn("@5", me2)


if __name__ == "__main__":
    unittest.main()
