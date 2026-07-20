"""Named flags for create/spawn (free order)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.argflags import (
    LORE_FLAG_ALIASES,
    looks_like_flag_command,
    parse_named_flags,
    story_when_from_flag,
)
from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world_bootstrap
from digital_office_spaces.world import World


class FlagParseTests(unittest.TestCase):
    def test_looks_like(self) -> None:
        self.assertTrue(looks_like_flag_command("--type thing --name X"))
        self.assertTrue(looks_like_flag_command("-t thing -n X"))
        self.assertFalse(looks_like_flag_command("thing Quill | soft"))

    def test_parse_order_free(self) -> None:
        p = parse_named_flags(
            '--when 0 --name Satisfaction --type sense/feeling '
            '--desc "The feeling of something working well."'
        )
        self.assertIsNone(p.error)
        self.assertEqual(p.get("type"), "sense/feeling")
        self.assertEqual(p.get("name"), "Satisfaction")
        self.assertEqual(p.get("when"), "0")
        self.assertIn("working well", p.get("desc"))

    def test_when_normalize(self) -> None:
        self.assertEqual(story_when_from_flag("0"), ("@0", 0))
        self.assertEqual(story_when_from_flag("@2"), ("@2", 2))
        self.assertEqual(story_when_from_flag("unknown"), ("@unknown", None))

    def test_boolean_add_and_lore_aliases(self) -> None:
        p = parse_named_flags(
            "-a -t Founding -b Raised for travelers. -w 0",
            aliases=LORE_FLAG_ALIASES,
        )
        self.assertIsNone(p.error)
        self.assertEqual(p.get("add"), "1")
        self.assertEqual(p.get("name"), "Founding")
        self.assertEqual(p.get("body"), "Raised for travelers.")
        self.assertEqual(p.get("when"), "0")
        # create/spawn: -t is still type
        c = parse_named_flags("-t thing -n Stick")
        self.assertEqual(c.get("type"), "thing")
        self.assertEqual(c.get("name"), "Stick")


class FlagCreateSpawnTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        self.conn = connect(Path(tmp.name))
        seed_world_bootstrap(self.conn)
        self.world = World(self.conn)

    def test_create_flag_form(self) -> None:
        r = dispatch(
            self.world,
            'create --type sense/feeling --when 0 --name Satisfaction '
            '--desc "The feeling of something working well."',
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Satisfaction", text)
        self.assertIn("@0", text)
        ven = self.world.find_ven("Satisfaction")
        assert ven is not None
        self.assertEqual(ven.kind, "sense")
        self.assertEqual((ven.subtype or "").lower(), "feeling")
        rows = self.world.history_for("ven", ven.id)
        self.assertEqual(rows[0]["story_when"], "@0")

    def test_spawn_flag_form(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create --type thing --name Stick --desc wood.").ok
        )
        r = dispatch(
            self.world,
            "spawn --ven stick -n Hiking Stick --when 3",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("@3", plain(r.message))
        self.assertIn("Hiking Stick", plain(r.message))

    def test_spawn_arrow_title(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create --type thing --name Twig --desc dry.").ok
        )
        r = dispatch(self.world, "spawn twig -> Walking Twig when @1")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Walking Twig", plain(r.message))
        self.assertIn("@1", plain(r.message))

    def test_legacy_still_works(self) -> None:
        r = dispatch(self.world, "create thing Old Form | yes. when @1")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("@1", plain(r.message))


if __name__ == "__main__":
    unittest.main()
