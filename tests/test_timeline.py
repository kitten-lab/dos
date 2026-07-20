"""Timeline / realm assignment via real dispatch path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from wbs_seed_fixtures import seed_world_classic as seed_world
from digital_office_spaces.world import World


def _seeded_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world(conn)
    return World(conn)


class TimelineManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _seeded_world()

    def test_timeline_list_shows_seed_layers(self) -> None:
        r = dispatch(self.world, "timeline list")
        self.assertTrue(r.ok)
        text = plain(r.message)
        self.assertIn("Prime", text)
        self.assertIn("Shattered", text)
        self.assertIn("CODE", text)
        self.assertRegex(text, r"\d+ location\(s\)")
        self.assertIn("inst_", text)

    def test_realm_list_line_shape(self) -> None:
        r = dispatch(self.world, "realm list")
        self.assertTrue(r.ok)
        text = plain(r.message)
        self.assertIn("Material", text)
        # Table: CODE  NAME  INSTANCE  LOCATIONS + rule under header
        self.assertIn("CODE", text)
        self.assertIn("NAME", text)
        self.assertIn("INSTANCE", text)
        self.assertIn("LOCATIONS", text)
        self.assertRegex(text, r"CODE\s+NAME\s+INSTANCE\s+LOCATIONS\n\s+-+")
        self.assertRegex(text, r"RLM-\d{3}")
        self.assertRegex(text, r"\(inst_[a-f0-9]+\)")
        self.assertRegex(text, r"\d+ location\(s\)")
        # blank line before helper
        self.assertRegex(
            text,
            r"location\(s\)\n\nrealm set",
        )

    def test_timeline_set_on_current_place(self) -> None:
        r = dispatch(self.world, "timeline set SHATTERED")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Shattered", text)
        where = plain(dispatch(self.world, "whereami").message)
        self.assertIn("Shattered", where)
        self.assertIn("Material", where)
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Shattered", look)

    def test_timeline_create_and_assign(self) -> None:
        c = dispatch(
            self.world,
            "timeline create RITUAL-EVE | Night the mirror box is opened.",
        )
        self.assertTrue(c.ok, msg=c.message)
        self.assertIn("RITUAL-EVE", plain(c.message))
        s = dispatch(self.world, "timeline set RITUAL-EVE")
        self.assertTrue(s.ok, msg=s.message)
        places = dispatch(self.world, "timeline places RITUAL-EVE")
        self.assertTrue(places.ok)
        ptext = plain(places.message)
        self.assertIn("Ritual Eve", ptext)
        self.assertIn("The Cathedral of Ordinary Light", ptext)
        self.assertIn("CODE", ptext)
        self.assertIn("NAME", ptext)
        self.assertRegex(ptext, r"CODE\s+NAME\s+INSTANCE\s+REALM\s+TIMELINE\n\s+-+")

    def test_dig_with_explicit_timeline(self) -> None:
        r = dispatch(
            self.world,
            "dig Mirror Box Chamber timeline SHATTERED",
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Mirror Box Chamber", text)
        self.assertIn("Shattered", text)
        places = plain(dispatch(self.world, "timeline places SHATTERED").message)
        self.assertIn("Mirror Box Chamber", places)

    def test_realm_set_and_whereami_coords(self) -> None:
        r = dispatch(self.world, "realm set MEMORY-ARCHIVE")
        self.assertTrue(r.ok, msg=r.message)
        where = plain(dispatch(self.world, "whereami").message)
        self.assertIn("Memory-Archive", where)
        self.assertIn("coords", where.lower())

    def test_examine_shows_coords_on_context_line(self) -> None:
        """kind | realm | timeline under title (no separate coords row)."""
        r = dispatch(self.world, "examine silver")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("#", text)
        self.assertIn("instance", text.lower())
        # Context strip: material | Material | …
        self.assertRegex(text, r"material\s+\|")
        self.assertIn("Material", text)
        # No blank line between those two meta lines
        self.assertNotRegex(
            text,
            r"(?im)#[A-Z0-9-]+\s+·\s+instance[^\n]*\n\s*\n\s*coords\b",
            msg=text,
        )


if __name__ == "__main__":
    unittest.main()
