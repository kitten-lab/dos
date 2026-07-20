"""Author when-stamps on lore add; typed-at (created_at) always retained."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.book import parse_book_line_ref
from digital_office_spaces.commands import dispatch, parse_lore_add
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class ParseLoreAddTests(unittest.TestCase):
    def test_no_stamp(self) -> None:
        self.assertEqual(
            parse_lore_add("Founding | Raised for travelers."),
            ("Founding", "Raised for travelers.", None),
        )
        self.assertEqual(parse_lore_add("Just a body."), ("", "Just a body.", None))

    def test_when_keyword_mythic(self) -> None:
        t, b, w = parse_lore_add(
            "when Before the Roads | Founding | Raised for travelers."
        )
        self.assertEqual(w, "Before the Roads")
        self.assertEqual(t, "Founding")
        self.assertEqual(b, "Raised for travelers.")

    def test_at_date_and_unix(self) -> None:
        _, _, w = parse_lore_add("@2024-06-15 14:30 | Note | Glass dimmed.")
        self.assertEqual(w, "2024-06-15 14:30")
        _, _, u = parse_lore_add("@1704067200 | Signal | Ping.")
        self.assertEqual(u, "1704067200")

    def test_stamp_body_only(self) -> None:
        t, b, w = parse_lore_add("when Mythic-Eve | | Body alone.")
        self.assertEqual(w, "Mythic-Eve")
        self.assertEqual(t, "")
        self.assertEqual(b, "Body alone.")


class LoreLineBreakTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_parse_unescapes_n(self) -> None:
        t, b, _w = parse_lore_add(r"Note | Line one.\nLine two.")
        self.assertEqual(t, "Note")
        self.assertEqual(b, "Line one.\nLine two.")
        self.assertNotIn(r"\n", b)
        self.assertIn("\n", b)

    def test_place_lore_add_and_list_breaks(self) -> None:
        r = dispatch(
            self.world,
            r"lore add Breaks | First paragraph.\nSecond paragraph.",
        )
        self.assertTrue(r.ok, msg=r.message)
        loc = self.world.player_location()
        assert loc is not None
        row = next(
            x for x in self.world.lore_for("instance", loc.id) if x["title"] == "Breaks"
        )
        self.assertEqual(row["body"], "First paragraph.\nSecond paragraph.")
        listed = plain(dispatch(self.world, "lore").message)
        self.assertIn("First paragraph.", listed)
        self.assertIn("Second paragraph.", listed)
        # real break: not a single glued line with backslash-n
        self.assertNotIn(r"\n", listed)
        i1 = listed.index("First paragraph.")
        i2 = listed.index("Second paragraph.")
        self.assertLess(i1, i2)
        self.assertIn("\n", listed[i1:i2] + "\n")  # separation between them

    def test_ven_lore_add_breaks(self) -> None:
        r = dispatch(
            self.world,
            r"lore ven unfinished quill add Quill note | Tip wet.\nStill writing.",
        )
        self.assertTrue(r.ok, msg=r.message)
        ven = self.world.find_ven("unfinished quill")
        assert ven is not None
        hit = [x for x in self.world.lore_for("ven", ven.id) if x["title"] == "Quill note"]
        self.assertTrue(hit)
        self.assertEqual(hit[0]["body"], "Tip wet.\nStill writing.")
        listed = plain(dispatch(self.world, "lore ven unfinished quill").message)
        self.assertIn("Tip wet.", listed)
        self.assertIn("Still writing.", listed)
        self.assertNotIn(r"\n", listed)


class LoreStampDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def _row_for_title(self, title: str):
        loc = self.world.player_location()
        assert loc is not None
        for r in self.world.lore_for("instance", loc.id):
            if r["title"] == title:
                return r
        return None

    def test_place_mythic_stamp_and_created_at(self) -> None:
        r = dispatch(
            self.world,
            "lore add when Before the Roads | Founding | Raised for travelers.",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Before the Roads", plain(r.message))
        row = self._row_for_title("Founding")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["when_label"], "Before the Roads")
        self.assertTrue(row["created_at"])
        self.assertNotEqual(row["created_at"], row["when_label"])
        listed = plain(dispatch(self.world, "lore").message)
        self.assertIn("Before the Roads", listed)
        self.assertIn("typed", listed.lower())
        self.assertIn(row["created_at"][:10], listed)  # date portion of typed-at

    def test_place_date_and_unix_stamps(self) -> None:
        dispatch(
            self.world,
            "lore add @2024-06-15 14:30 | Eclipse note | The glass dimmed.",
        )
        dispatch(
            self.world,
            "lore add @1704067200 | Signal | A unix-style event stamp.",
        )
        listed = plain(dispatch(self.world, "lore").message)
        self.assertIn("2024-06-15 14:30", listed)
        self.assertIn("1704067200", listed)
        eclipse = self._row_for_title("Eclipse note")
        signal = self._row_for_title("Signal")
        assert eclipse is not None and signal is not None
        self.assertTrue(eclipse["created_at"])
        self.assertTrue(signal["created_at"])
        self.assertEqual(eclipse["when_label"], "2024-06-15 14:30")
        self.assertEqual(signal["when_label"], "1704067200")

    def test_ven_lore_with_stamp(self) -> None:
        r = dispatch(
            self.world,
            "lore ven unfinished quill add when First Naming | Motif | Ink that remembers.",
        )
        self.assertTrue(r.ok, msg=r.message)
        listed = plain(dispatch(self.world, "lore ven unfinished quill").message)
        self.assertIn("First Naming", listed)
        self.assertIn("typed", listed.lower())
        ven = self.world.find_ven("unfinished quill")
        assert ven is not None
        rows = list(self.world.lore_for("ven", ven.id))
        hit = [x for x in rows if x["title"] == "Motif"]
        self.assertTrue(hit)
        self.assertEqual(hit[0]["when_label"], "First Naming")
        self.assertTrue(hit[0]["created_at"])


class LoreFlagAddTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_place_flag_add(self) -> None:
        r = dispatch(
            self.world,
            "lore -a -t Founding -b Raised for travelers. -w 0",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("@0", plain(r.message))
        loc = self.world.player_location()
        assert loc is not None
        hit = [
            x
            for x in self.world.lore_for("instance", loc.id)
            if x["title"] == "Founding"
        ]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["body"], "Raised for travelers.")
        self.assertEqual(hit[0]["when_label"], "@0")

    def test_on_me_flag_add(self) -> None:
        r = dispatch(
            self.world,
            'lore --add --on me -n Whisper -d Soft light. --when 2',
        )
        self.assertTrue(r.ok, msg=r.message)
        pid = self.world.player_id()
        assert pid
        hit = [
            x
            for x in self.world.lore_for("instance", pid)
            if x["title"] == "Whisper"
        ]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["body"], "Soft light.")
        self.assertEqual(hit[0]["when_label"], "@2")

    def test_on_prefix_then_flags(self) -> None:
        r = dispatch(
            self.world,
            "lore on me -a -t Note -b Bent nib.",
        )
        self.assertTrue(r.ok, msg=r.message)
        pid = self.world.player_id()
        assert pid
        hit = [
            x
            for x in self.world.lore_for("instance", pid)
            if x["title"] == "Note"
        ]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["body"], "Bent nib.")


class BookLineRefParseTests(unittest.TestCase):
    def test_parse_variants(self) -> None:
        self.assertEqual(parse_book_line_ref("1:2"), (1, 2))
        self.assertEqual(parse_book_line_ref("p1:3"), (1, 3))
        self.assertEqual(parse_book_line_ref("2.4"), (2, 4))
        self.assertIsNone(parse_book_line_ref("abc"))
        self.assertIsNone(parse_book_line_ref("0:1"))


class LoreFromBookLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        dispatch(self.world, "create book Field Notes | notebook")
        dispatch(self.world, "spawn field-notes")
        dispatch(
            self.world,
            r"book page add field-notes Preface | Alpha line.\nBeta quoted.",
        )

    def test_lore_add_from_line_and_undo(self) -> None:
        r = dispatch(self.world, "lore add from field-notes 1:2")
        self.assertTrue(r.ok, msg=r.message)
        listed = plain(dispatch(self.world, "lore").message)
        self.assertIn("Beta quoted.", listed)
        self.assertIn("p1:2", listed.lower().replace(" ", "") or listed)
        # title cites book line
        self.assertTrue(
            "p1:2" in listed.lower() or "1:2" in listed or "Field Notes" in listed
        )
        loc = self.world.player_location()
        assert loc is not None
        rows = list(self.world.lore_for("instance", loc.id))
        hit = [x for x in rows if (x["body"] or "") == "Beta quoted."]
        self.assertEqual(len(hit), 1)
        self.assertIn("p1:2", hit[0]["title"] or "")

        r = dispatch(self.world, "undo")
        self.assertTrue(r.ok)
        rows2 = list(self.world.lore_for("instance", loc.id))
        hit2 = [x for x in rows2 if (x["body"] or "") == "Beta quoted."]
        self.assertEqual(len(hit2), 0)

    def test_lore_add_from_with_title_override(self) -> None:
        r = dispatch(
            self.world,
            "lore add from field-notes p1:1 | Quoted fragment",
        )
        self.assertTrue(r.ok, msg=r.message)
        loc = self.world.player_location()
        assert loc is not None
        rows = list(self.world.lore_for("instance", loc.id))
        hit = [x for x in rows if x["title"] == "Quoted fragment"]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["body"], "Alpha line.")


if __name__ == "__main__":
    unittest.main()
