"""@desc show / set / append / clear / line breaks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.textutil import escape_desc, unescape_desc
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class UnescapeTests(unittest.TestCase):
    def test_newline_and_backslash(self) -> None:
        self.assertEqual(unescape_desc(r"a\nb"), "a\nb")
        self.assertEqual(unescape_desc(r"a\\b"), "a\\b")
        self.assertEqual(unescape_desc(r"a\\nb"), "a\\nb")

    def test_escape_roundtrip_for_multiline_commit(self) -> None:
        raw = "# Title\n\n**Bold**\n---\ntail"
        encoded = escape_desc(raw)
        self.assertNotIn("\n", encoded)
        self.assertEqual(unescape_desc(encoded), raw)
        # Existing typed \\n literal survives escape→unescape
        typed = r"keep\nliteral"
        self.assertEqual(unescape_desc(escape_desc(typed)), typed)


class DescCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_show_and_set(self) -> None:
        r = dispatch(self.world, "@desc")
        self.assertTrue(r.ok)
        self.assertIn("Description", plain(r.message))

        r = dispatch(self.world, r"@desc Line one.\nLine two.")
        self.assertTrue(r.ok)
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(loc.description, "Line one.\nLine two.")

        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Line one.", look)
        self.assertIn("Line two.", look)

    def test_append_and_clear(self) -> None:
        dispatch(self.world, "@desc First.")
        dispatch(self.world, "@desc + Second.")
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(loc.description, "First.\nSecond.")

        dispatch(self.world, "@desc ++ Third para.")
        loc = self.world.player_location()
        assert loc is not None
        self.assertEqual(loc.description, "First.\nSecond.\n\nThird para.")

        dispatch(self.world, "@desc clear")
        loc = self.world.player_location()
        assert loc is not None
        # VEN default returns
        self.assertIn("half-inked", loc.description.lower())

    def test_multiline_on_target_studio_no_name_leak(self) -> None:
        """@desc on <name> <<studio must not glue name/studio into body."""
        from digital_office_spaces.multiline_open import (
            commit_multiline_session,
            parse_multiline_opener,
        )
        from digital_office_spaces.studio_text import is_studio, strip_studio_header

        self.assertTrue(
            dispatch(
                self.world, "create person The Castaway | A survivor."
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn the-castaway as The Castaway").ok
        )
        sess = parse_multiline_opener("@desc on the castaway <<studio")
        self.assertIsNotNone(sess)
        assert sess is not None
        self.assertTrue(sess.studio)
        body = ":Design start: 2024-01-03\n\n**Hello**"
        r = commit_multiline_session(self.world, sess, body)
        self.assertTrue(r.ok, msg=r.message)
        inst = self.world.resolve_here_named("castaway")
        assert inst is not None
        self.assertTrue(is_studio(inst.description))
        plain_body = strip_studio_header(inst.description)
        self.assertTrue(plain_body.startswith(":Design start:"))
        self.assertNotIn("the castaway | studio", plain_body.lower())
        self.assertNotIn("castaway | studio", plain_body.lower())

    def test_desc_commit_records_history(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        self.assertTrue(
            dispatch(self.world, "@desc Soft dusk on the boards.").ok
        )
        # Edit alone does not write material history
        before = self.world.history_for("instance", loc.id)
        n_desc = sum(1 for h in before if h["verb"] == "desc")
        r = dispatch(self.world, "@desc commit when @3")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("committed", plain(r.message).lower())
        self.assertIn("HST-", plain(r.message))
        after = self.world.history_for("instance", loc.id)
        desc_rows = [h for h in after if h["verb"] == "desc"]
        self.assertEqual(len(desc_rows), n_desc + 1)
        self.assertEqual(desc_rows[-1]["story_when"], "@3")
        self.assertIn("Soft dusk", desc_rows[-1]["note"] or "")
        listed = plain(dispatch(self.world, "history here").message)
        self.assertIn("desc", listed.lower())
        self.assertIn("@3", listed)
        # Full body in text log
        revs = self.world.list_text_revisions(
            "instance", loc.id, field="description"
        )
        self.assertGreaterEqual(len(revs), 1)
        self.assertIn("Soft dusk", revs[-1]["body"] or "")
        # Full body also as instance lore (default title)
        lore_rows = self.world.lore_for("instance", loc.id)
        hit = [
            r
            for r in lore_rows
            if "Soft dusk" in (r["body"] or "")
        ]
        self.assertTrue(hit)
        self.assertEqual(hit[-1]["title"], "description update")
        self.assertIn("lore", plain(r.message).lower())

        r2 = dispatch(
            self.world, "@desc commit -t Soft dusk beat when @1"
        )
        self.assertTrue(r2.ok, msg=r2.message)
        lore2 = self.world.lore_for("instance", loc.id)
        titled = [r for r in lore2 if r["title"] == "Soft dusk beat"]
        self.assertEqual(len(titled), 1)
        self.assertIn("Soft dusk", titled[0]["body"] or "")


if __name__ == "__main__":
    unittest.main()
