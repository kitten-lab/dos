"""Unified status / sit / whereami situation command."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from wbs_seed_fixtures import seed_world_classic as seed_world
from dos.status import (
    SIDEBAR_TITLE,
    format_sidebar,
    format_status_command,
    format_strip,
    situation,
)
from dos.world import World


def _seeded_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world(conn)
    return World(conn)


_CORE_MARKERS = (
    "Builder",
    "The Cathedral of Ordinary Light",
    "Material",
    "Prime",
)


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _seeded_world()

    def test_situation_snapshot_seed(self) -> None:
        s = situation(self.world)
        self.assertEqual(s.who, "Builder")
        self.assertEqual(s.place, "The Cathedral of Ordinary Light")
        self.assertEqual(s.realm, "Material")
        self.assertEqual(s.timeline, "Prime")
        self.assertEqual(s.coords, "Material / Prime")
        self.assertGreaterEqual(s.exit_count, 1)
        self.assertIn("CATHEDRAL", s.place_ven_label.upper())
        self.assertIn("(", s.place_ven_label)  # name (slug)

    def test_sidebar_and_strip_contain_fields(self) -> None:
        side = plain(format_sidebar(self.world))
        self.assertIn("Builder", side)
        self.assertIn("The Cathedral of Ordinary Light", side)
        self.assertIn("Material", side)
        self.assertIn("Prime", side)
        self.assertIn(SIDEBAR_TITLE, side.lower())
        self.assertIn("character", side.lower())
        self.assertIn("location", side.lower())
        self.assertIn("inventory", side.lower())

        strip = plain(format_strip(self.world))
        self.assertIn("Builder", strip)
        self.assertIn("The Cathedral of Ordinary Light", strip)
        self.assertIn("Material / Prime", strip)

    def test_status_sit_whereami_equivalent(self) -> None:
        """All aliases share one body (not two divergent features)."""
        msgs = {}
        for cmd in ("status", "sit", "situation", "whereami", "where"):
            r = dispatch(self.world, cmd)
            self.assertTrue(r.ok, msg=f"{cmd}: {r.message}")
            msgs[cmd] = r.message
        # Identical markup from same formatter
        self.assertEqual(msgs["status"], msgs["sit"])
        self.assertEqual(msgs["status"], msgs["situation"])
        self.assertEqual(msgs["status"], msgs["whereami"])
        self.assertEqual(msgs["status"], msgs["where"])

        text = plain(msgs["status"])
        self.assertTrue("Locate" in text or "Status" in text, msg=text)
        self.assertNotIn("At a glance", text)
        for m in _CORE_MARKERS:
            self.assertIn(m, text)
        self.assertIn("you", text.lower())
        self.assertIn("place", text.lower())
        self.assertIn("ven", text.lower())
        self.assertIn("coords", text.lower())
        self.assertIn("inventory", text.lower())
        self.assertIn("paths", text.lower())

    def test_status_command_dispatch(self) -> None:
        r = dispatch(self.world, "status")
        self.assertTrue(r.ok)
        text = plain(r.message)
        # status is an alias for locate self
        self.assertTrue("Locate" in text or "Status" in text, msg=text)
        self.assertIn("Builder", text)
        self.assertIn("Material", text)
        self.assertIn("Prime", text)
        self.assertNotIn("At a glance", text)

    def test_status_updates_after_move(self) -> None:
        dispatch(self.world, "go through the mirror")
        s = situation(self.world)
        self.assertEqual(s.place, "Hall of Shelved Years")
        self.assertEqual(s.realm, "Memory-Archive")
        self.assertEqual(s.timeline, "Prime")
        self.assertIn(
            "Hall of Shelved Years",
            plain(dispatch(self.world, "status").message),
        )

    def test_status_updates_after_timeline_set(self) -> None:
        dispatch(self.world, "timeline set SHATTERED")
        s = situation(self.world)
        self.assertEqual(s.timeline, "Shattered")
        self.assertEqual(s.coords, "Material / Shattered")
        self.assertEqual(
            plain(format_status_command(self.world)).count("Shattered") >= 1,
            True,
        )

    def test_help_status_no_at_a_glance_dual_feature(self) -> None:
        for term in ("status", "whereami", "sit"):
            r = dispatch(self.world, f"help {term}")
            self.assertTrue(r.ok, msg=term)
            text = plain(r.message).lower()
            self.assertNotIn("at a glance", text)
            self.assertNotIn("at-a-glance", text)
            # should not pitch two different jobs
            self.assertNotIn("shorter situation block", text)
            # help routes status/sit/whereami → locate topic
            self.assertTrue(
                "locate" in text or "same command" in text or "same as" in text,
                msg=text,
            )


if __name__ == "__main__":
    unittest.main()
