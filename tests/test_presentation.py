"""Presentation tests drive the real dispatch/seed path (no reimplementation)."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain, safe
from wbs_seed_fixtures import seed_world_classic as seed_world
from digital_office_spaces.world import World


def _seeded_world() -> World:
    # temp file so tests never touch the user's seed.world.db
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = connect(path)
    seed_world(conn)
    return World(conn)


class LookHierarchyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _seeded_world()

    def test_look_has_title_prose_meta_exits_sections(self) -> None:
        result = dispatch(self.world, "look")
        self.assertTrue(result.ok)
        text = plain(result.message)

        # Distinct title line (cathedral) — plain readable display form
        self.assertIn("The Cathedral of Ordinary Light", text)
        self.assertNotIn("THE-CATHEDRAL-OF-ORDINARY-LIGHT", text)
        # Prose separate from lists (descriptions stay mixed case)
        self.assertIn("White stone", text)
        self.assertIn("cracked mirror", text)
        # Look location: subtype only (none here) · realm | timeline — no root "place"
        self.assertIn("Material", text)
        self.assertIn("Prime", text)
        self.assertRegex(text, r"Material\s+\|\s+Prime")
        self.assertNotRegex(text, r"place\s+\|\s+Material")
        # paths inline on look (grouped list)
        self.assertIn("Paths", text)
        self.assertIn("through the mirror", text)
        # Loose presence under Here
        self.assertIn("Silver Thread", text)
        self.assertIn("Liturgical Hush", text)

        # Hierarchy: location line → description → paths
        i_title = text.index("The Cathedral of Ordinary Light")
        i_realm = text.lower().index("material")  # realm on location line
        i_prose = text.index("White stone")
        i_paths = text.index("Paths")
        self.assertLess(i_title, i_realm)
        self.assertLess(i_realm, i_prose)
        self.assertLess(i_prose, i_paths)
        self.assertIn("Location:", text)

    def test_locate_self_aligned_fields(self) -> None:
        result = dispatch(self.world, "locate self")
        self.assertTrue(result.ok)
        text = plain(result.message)
        self.assertIn("Locate", text)
        self.assertIn("place", text)
        self.assertIn("The Cathedral of Ordinary Light", text)
        self.assertIn("Material", text)
        self.assertIn("Prime", text)
        # bare locate and temporary aliases match
        bare = plain(dispatch(self.world, "locate").message)
        self.assertEqual(text, bare)
        w = plain(dispatch(self.world, "status").message)
        self.assertEqual(text, w)

    def test_go_then_look_readable_multisection(self) -> None:
        result = dispatch(self.world, "go through the mirror")
        self.assertTrue(result.ok)
        text = plain(result.message)
        self.assertIn("Hall of Shelved Years", text)
        self.assertIn("Memory-Archive", text)
        # look after go still includes inline paths
        self.assertIn("Paths", text)
        # travel cue then room
        self.assertIn("through the mirror", text)

    def test_world_names_with_brackets_do_not_break_markup(self) -> None:
        # dig keeps formal name; markup-looking brackets must still be safe in Rich
        evil = "Evil [bold red]Hack[/bold red]"
        r = dispatch(self.world, f"dig {evil}")
        self.assertTrue(r.ok)
        rendered = plain(r.message)
        # formal name preserved (not forced to cute ALL-CAPS)
        self.assertIn("Evil", rendered)
        self.assertIn("Hack", rendered)
        self.assertNotIn("EVIL-BOLD-RED-HACK", rendered)
        # Dynamic world/user strings still escape via hint/ok when not normalized
        from digital_office_spaces.format import hint

        h = hint(f"→ {evil}")
        self.assertIn(r"\[bold red]", h)
        self.assertIn(safe(evil), h)
        self.assertEqual(plain(h).count("Hack"), 1)

    def test_hint_escapes_like_ok_err(self) -> None:
        from digital_office_spaces.format import hint, ok, err

        payload = "x [bold]inject[/bold] y"
        for fn in (hint, ok, err):
            out = fn(payload)
            self.assertIn(safe(payload), out)
            self.assertIn(r"\[bold]", out)

    def test_no_raw_half_tags_from_unescaped_exit_types_in_plain(self) -> None:
        result = dispatch(self.world, "exits")
        text = plain(result.message)
        # type shorthands on each row (sp spatial, di dimensional)
        self.assertRegex(text, r"\bsp\b")
        self.assertRegex(text, r"\bdi\b")
        self.assertIn("→", text)
        # no orphan closing tags typical of broken markup
        self.assertIsNone(re.search(r"\[/bold(?!\s)", text))


if __name__ == "__main__":
    unittest.main()
