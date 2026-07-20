"""Talk sessions: dialog turns, /fin, when replace, people depth, re-read."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.dialog import (
    FIN_TOKEN,
    dialog_teaser_line,
    format_script_transcript,
    format_script_turn,
    parse_dialog_when_line,
    parse_talk_args,
    parse_transcript_turns,
    parse_when_stamp,
)
from dos.format import plain
from wbs_seed_fixtures import seed_world_story
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class ParseTalkArgsTests(unittest.TestCase):
    def test_person_only(self) -> None:
        p, t, w = parse_talk_args("cartographer")
        self.assertEqual(p, "cartographer")
        self.assertEqual(t, "")
        self.assertIsNone(w)

    def test_title_and_when(self) -> None:
        p, t, w = parse_talk_args(
            "cartographer | when Before the Roads | First Meeting"
        )
        self.assertEqual(p, "cartographer")
        self.assertEqual(t, "First Meeting")
        self.assertEqual(w, "Before the Roads")

    def test_unix_stamp(self) -> None:
        p, t, w = parse_talk_args("archivist | @1704067200 | Signal")
        self.assertEqual(w, "1704067200")
        self.assertEqual(t, "Signal")


class ScriptFormatTests(unittest.TestCase):
    def test_parse_and_script_layout(self) -> None:
        raw = "Builder: Hello.\nCartographer: Good day."
        turns = parse_transcript_turns(raw)
        self.assertEqual(turns, [("Builder", "Hello."), ("Cartographer", "Good day.")])
        script = plain(format_script_transcript(raw))
        self.assertIn("Builder", script)
        self.assertIn("Hello.", script)
        self.assertNotIn("Builder: Hello", script)
        self.assertRegex(script, r"Builder\s*\n\s+Hello")

    def test_script_turn_live(self) -> None:
        t = plain(format_script_turn("Builder", "Hi there.", you_label="you"))
        self.assertIn("Builder", t)
        self.assertIn("you", t)
        self.assertIn("Hi there.", t)
        self.assertRegex(t, r"Builder.*\n\s+Hi there")


class ParseWhenStampTests(unittest.TestCase):
    def test_variants(self) -> None:
        self.assertEqual(parse_when_stamp("when Before the Roads"), "Before the Roads")
        self.assertEqual(parse_when_stamp("@1704067200"), "1704067200")
        self.assertEqual(parse_when_stamp("After the Break"), "After the Break")
        self.assertIsNone(parse_when_stamp("clear"))
        self.assertEqual(
            parse_dialog_when_line("/when when Later Era"),
            "Later Era",
        )
        self.assertIsNone(parse_dialog_when_line("/when clear"))


class TalkRoundtripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        # Cartographer is at Twin Overlook
        r = dispatch(self.world, "go along the story road")
        self.assertTrue(r.ok, msg=r.message)

    def test_talk_fin_lore_and_reread(self) -> None:
        start = dispatch(
            self.world,
            "talk cartographer | when Before the Roads | First Meeting",
        )
        self.assertTrue(start.ok, msg=start.message)
        self.assertIsNotNone(self.world.active_dialog)
        self.assertIn("Talking", plain(start.message))

        t1 = dispatch(self.world, "The maps still remember us.")
        self.assertTrue(t1.ok)
        self.assertIn("maps still remember", plain(t1.message))
        t2 = dispatch(self.world, "And the roads that have not been drawn.")
        self.assertTrue(t2.ok)

        # World commands are swallowed as dialog while active
        self.assertIsNotNone(self.world.active_dialog)

        fin = dispatch(self.world, FIN_TOKEN)
        self.assertTrue(fin.ok, msg=fin.message)
        self.assertIsNone(self.world.active_dialog)
        fin_txt = plain(fin.message)
        self.assertIn("Dialog ended", fin_txt)
        self.assertIn("First Meeting", fin_txt)

        # Lore on place names both parties (compact dialog pointer, not full dump)
        lore = plain(dispatch(self.world, "lore").message)
        self.assertIn("Dialog", lore)
        self.assertIn("Builder", lore)
        self.assertIn("Cartographer", lore)
        self.assertIn("Before the Roads", lore)
        self.assertIn("dialogs show", lore.lower())
        # meta body lines stay quiet / not raw "Transcript id:" wall
        self.assertNotIn("Transcript id:", lore)
        self.assertNotIn("A dialog took place between", lore)

        # Re-read transcript contains both turns (script layout)
        listing = plain(dispatch(self.world, "dialogs").message)
        self.assertIn("First Meeting", listing)
        shown = plain(dispatch(self.world, "dialogs show 1").message)
        self.assertIn("maps still remember", shown)
        self.assertIn("roads that have not been drawn", shown)
        self.assertIn("Before the Roads", shown)
        # Script style: speaker on own line, speech indented (not "Name: text")
        self.assertNotIn("Builder: The maps", shown)
        self.assertIn("Builder", shown)
        self.assertRegex(shown, r"Builder\s*\n\s+The maps")

        # After /fin, normal commands work
        look = dispatch(self.world, "look")
        self.assertTrue(look.ok)
        self.assertIn("Overlook", plain(look.message))

    def test_active_when_replace_persists_at_fin(self) -> None:
        dispatch(
            self.world,
            "talk cartographer | when Before the Roads | First Meeting",
        )
        self.assertEqual(
            self.world.active_dialog.when_label if self.world.active_dialog else None,
            "Before the Roads",
        )
        r = dispatch(self.world, "/when After the Break")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("After the Break", plain(r.message))
        assert self.world.active_dialog is not None
        self.assertEqual(self.world.active_dialog.when_label, "After the Break")
        # old stamp gone from session status line
        self.assertNotEqual(
            self.world.active_dialog.when_label, "Before the Roads"
        )
        dispatch(self.world, "Still walking the ridge.")
        dispatch(self.world, "Maps fold themselves.")
        fin = dispatch(self.world, FIN_TOKEN)
        self.assertTrue(fin.ok, msg=fin.message)
        rows = self.world.list_dialogs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["when_label"], "After the Break")
        shown = plain(dispatch(self.world, "dialogs show 1").message)
        self.assertIn("After the Break", shown)
        self.assertNotIn("Before the Roads", shown)

    def test_completed_dialog_when_replace(self) -> None:
        dispatch(
            self.world,
            "talk cartographer | when Old Stamp | Ridge Talk",
        )
        dispatch(self.world, "Hello on the ridge.")
        dispatch(self.world, "Hello returned.")
        dispatch(self.world, FIN_TOKEN)
        row = self.world.list_dialogs()[0]
        self.assertEqual(row["when_label"], "Old Stamp")

        r = dispatch(
            self.world,
            "dialogs when 1 | when New Era",
        )
        self.assertTrue(r.ok, msg=r.message)
        updated = self.world.get_dialog(row["id"])
        assert updated is not None
        self.assertEqual(updated["when_label"], "New Era")
        shown = plain(dispatch(self.world, "dialogs show 1").message)
        self.assertIn("New Era", shown)
        self.assertNotIn("Old Stamp", shown)

        # undo restores prior when
        dispatch(self.world, "undo")
        restored = self.world.get_dialog(row["id"])
        assert restored is not None
        self.assertEqual(restored["when_label"], "Old Stamp")

    def test_dialogs_list_scoped_to_place(self) -> None:
        """Bare dialogs = this place; dialogs all / show list = everywhere."""
        # Dialog at hearth
        dispatch(
            self.world,
            "talk cartographer | when Here | Hearth Talk",
        )
        dispatch(self.world, "At the hearth.")
        dispatch(self.world, "Yes.")
        dispatch(self.world, FIN_TOKEN)
        hearth = self.world.player_location()
        assert hearth is not None

        # Dig + go + dialog elsewhere
        self.assertTrue(dispatch(self.world, "dig Side Alcove").ok)
        self.assertTrue(
            dispatch(self.world, "link alcove-in -> Side Alcove both").ok
        )
        # Person must be here to talk; stage them next door without inv hop
        self.assertTrue(
            dispatch(self.world, "put cartographer in alcove-in").ok
        )
        go = dispatch(self.world, "go alcove-in")
        self.assertTrue(go.ok, go.message)
        t = dispatch(
            self.world,
            "talk cartographer | when There | Alcove Whisper",
        )
        self.assertTrue(t.ok, t.message)
        dispatch(self.world, "In the alcove.")
        dispatch(self.world, "Softly.")
        fin2 = dispatch(self.world, FIN_TOKEN)
        self.assertTrue(fin2.ok, fin2.message)

        # In alcove: only alcove dialog
        here = plain(dispatch(self.world, "dialogs").message)
        self.assertIn("Alcove Whisper", here)
        self.assertIn("Dialogs ·", here)
        self.assertNotIn("Hearth Talk", here)

        # Global lists
        for cmd in ("dialogs all", "dialogs list", "dialogs show list"):
            all_msg = plain(dispatch(self.world, cmd).message)
            self.assertIn("Hearth Talk", all_msg, msg=cmd)
            self.assertIn("Alcove Whisper", all_msg, msg=cmd)
            self.assertIn("all", all_msg.lower(), msg=cmd)

        # Back at hearth: only hearth dialog in bare list
        # reverse link uses same label when both
        self.assertTrue(dispatch(self.world, "go alcove-in").ok)
        hearth_list = plain(dispatch(self.world, "dialogs").message)
        self.assertIn("Hearth Talk", hearth_list)
        self.assertNotIn("Alcove Whisper", hearth_list)

    def test_dialog_cute_slug_show(self) -> None:
        """Dialogs get typeable cute slugs; show works by slug not only dlg_ id."""
        dispatch(
            self.world,
            "talk cartographer | when Before the Roads | First Meeting",
        )
        dispatch(self.world, "Hello.")
        dispatch(self.world, "Hello back.")
        fin = dispatch(self.world, FIN_TOKEN)
        self.assertTrue(fin.ok, msg=fin.message)
        fin_msg = plain(fin.message)
        self.assertIn("FIRST-MEETING", fin_msg)
        self.assertNotIn("dlg_", fin_msg)

        row = self.world.list_dialogs()[0]
        self.assertEqual(row["slug"], "FIRST-MEETING")
        listed = plain(dispatch(self.world, "dialogs").message)
        self.assertIn("FIRST-MEETING", listed)
        self.assertNotIn(row["id"], listed)

        shown = plain(dispatch(self.world, "dialogs show FIRST-MEETING").message)
        self.assertIn("First Meeting", shown)
        self.assertIn("FIRST-MEETING", shown)
        # lower / partial cute also resolves
        shown2 = plain(dispatch(self.world, "dialogs show first-meeting").message)
        self.assertIn("First Meeting", shown2)

        # second dialog with same title gets suffix
        dispatch(
            self.world,
            "talk cartographer | First Meeting",
        )
        dispatch(self.world, "Again.")
        dispatch(self.world, "Again.")
        dispatch(self.world, FIN_TOKEN)
        rows = self.world.list_dialogs()
        slugs = {r["slug"] for r in rows}
        self.assertIn("FIRST-MEETING", slugs)
        self.assertIn("FIRST-MEETING-2", slugs)

    def test_completed_dialog_rename(self) -> None:
        """Title can be set after /fin (forgot at talk start); lore titles follow."""
        dispatch(self.world, "talk cartographer")
        dispatch(self.world, "We spoke without a title.")
        dispatch(self.world, "Indeed.")
        dispatch(self.world, FIN_TOKEN)
        row = self.world.list_dialogs()[0]
        did = row["id"]

        # Lore notes from /fin cite the transcript id
        lore_before = self.world.conn.execute(
            """
            SELECT * FROM lore_revisions
            WHERE author = 'dialog' AND body LIKE ?
            """,
            (f"%Transcript id: {did}%",),
        ).fetchall()
        self.assertGreaterEqual(len(lore_before), 1)

        r = dispatch(self.world, "dialogs rename 1 as Better Title")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Better Title", plain(r.message))
        updated = self.world.get_dialog(did)
        assert updated is not None
        self.assertEqual(updated["title"], "Better Title")
        listed = plain(dispatch(self.world, "dialogs").message)
        self.assertIn("Better Title", listed)
        shown = plain(dispatch(self.world, "dialogs show 1").message)
        self.assertIn("Better Title", shown)

        lore_after = self.world.conn.execute(
            """
            SELECT * FROM lore_revisions
            WHERE author = 'dialog' AND body LIKE ?
            """,
            (f"%Transcript id: {did}%",),
        ).fetchall()
        self.assertGreaterEqual(len(lore_after), 1)
        for lr in lore_after:
            self.assertEqual(lr["title"], "Dialog · Better Title")
            self.assertNotIn("Untitled", lr["title"] or "")

        # alias
        r2 = dispatch(self.world, "dialogs title 1 as Even Better")
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertEqual(self.world.get_dialog(did)["title"], "Even Better")
        lore2 = self.world.conn.execute(
            """
            SELECT title FROM lore_revisions
            WHERE author = 'dialog' AND body LIKE ?
            """,
            (f"%Transcript id: {did}%",),
        ).fetchall()
        for lr in lore2:
            self.assertEqual(lr["title"], "Dialog · Even Better")

        # undo restores previous title (Better Title) and lore
        dispatch(self.world, "undo")
        self.assertEqual(self.world.get_dialog(did)["title"], "Better Title")
        lore_undo = self.world.conn.execute(
            """
            SELECT title FROM lore_revisions
            WHERE author = 'dialog' AND body LIKE ?
            """,
            (f"%Transcript id: {did}%",),
        ).fetchall()
        for lr in lore_undo:
            self.assertEqual(lr["title"], "Dialog · Better Title")

        bad = dispatch(self.world, "dialogs rename 99 as Nope")
        self.assertIn("No dialog", plain(bad.message))

    def test_fin_without_turns_cancels(self) -> None:
        dispatch(self.world, "talk cartographer")
        fin = dispatch(self.world, "/fin")
        self.assertTrue(fin.ok)
        self.assertIsNone(self.world.active_dialog)
        self.assertIn("cancelled", plain(fin.message).lower())
        self.assertEqual(len(self.world.list_dialogs()), 0)

    def test_cannot_talk_to_object(self) -> None:
        # Letter is material on overlook
        r = dispatch(self.world, "talk letter")
        self.assertTrue(r.ok)  # errors surface as message, not exception
        self.assertRegex(
            plain(r.message).lower(),
            r"not a person|no one matching|no 'letter'|no \"letter\"",
        )
        self.assertIsNone(self.world.active_dialog)


class PeopleDepthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        r = dispatch(self.world, "go along the story road")
        self.assertTrue(r.ok, msg=r.message)

    def test_who_and_examine_inner_life_and_dialog_teaser(self) -> None:
        who = plain(dispatch(self.world, "who").message)
        self.assertIn("Cartographer", who)
        # seed: Patient Longing (feeling) + Road-Mapper (archetype)
        self.assertIn("Longing", who)
        self.assertIn("feeling", who.lower())
        # display_name softens hyphens (Road-Mapper → Road Mapper)
        self.assertTrue(
            "Road-Mapper" in who or "Road Mapper" in who,
            msg=who,
        )
        self.assertIn("archetype", who.lower())
        # no dialog yet → no last dialog teaser required
        self.assertNotIn("last dialog", who.lower())

        ex = plain(dispatch(self.world, "examine cartographer").message)
        self.assertIn("Inner life", ex)
        self.assertIn("Longing", ex)
        self.assertTrue(
            "Road-Mapper" in ex or "Road Mapper" in ex,
            msg=ex,
        )

        # Complete a dialog → teaser on who + examine
        dispatch(
            self.world,
            "talk cartographer | when Told-Time | Overlook Whisper",
        )
        dispatch(self.world, "The ridge holds both of us.")
        dispatch(self.world, "Even when maps disagree.")
        dispatch(self.world, FIN_TOKEN)

        who2 = plain(dispatch(self.world, "who").message)
        self.assertIn("last dialog", who2.lower())
        self.assertIn("Overlook Whisper", who2)
        self.assertIn("Told-Time", who2)

        ex2 = plain(dispatch(self.world, "examine cartographer").message)
        self.assertIn("last dialog", ex2.lower())
        self.assertIn("Overlook Whisper", ex2)
        teaser = dialog_teaser_line(
            title="Overlook Whisper",
            when_label="Told-Time",
            transcript="Builder: The ridge holds both of us.",
        )
        self.assertIn("Overlook Whisper", teaser)
        self.assertIn("Told-Time", teaser)


if __name__ == "__main__":
    unittest.main()
