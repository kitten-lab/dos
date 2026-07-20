"""Local multiverse map: depth-limited exit tree."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.mapview import (
    DEFAULT_MAP_DEPTH,
    MAX_MAP_DEPTH,
    collect_map_tree,
    format_map_tree,
    parse_map_args,
)
from digital_office_spaces.seed import seed_world_story
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class ParseMapArgsTests(unittest.TestCase):
    def test_defaults_and_depth(self) -> None:
        self.assertEqual(parse_map_args(""), (DEFAULT_MAP_DEPTH, None))
        self.assertEqual(parse_map_args("here"), (DEFAULT_MAP_DEPTH, None))
        self.assertEqual(parse_map_args("1"), (1, None))
        self.assertEqual(parse_map_args("here 3"), (3, None))
        d, err = parse_map_args("99")
        self.assertIsNotNone(err)
        d, err = parse_map_args("timeline")
        self.assertIsNotNone(err)


class MapTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_collect_depth_and_format(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        tree0 = collect_map_tree(self.world, loc.id, depth=0)
        self.assertEqual(tree0.depth, 0)
        self.assertEqual(tree0.branches, [])
        formatted0 = format_map_tree(tree0)
        self.assertIn("depth 0", plain(formatted0).lower())

        tree1 = collect_map_tree(self.world, loc.id, depth=1)
        self.assertGreaterEqual(len(tree1.branches), 1)
        # depth 1: no expanded children (or only empty)
        for br in tree1.branches:
            self.assertEqual(br.children, [])

        tree2 = collect_map_tree(self.world, loc.id, depth=2)
        self.assertEqual(tree2.depth, 2)
        view = format_map_tree(tree2)
        plain_v = plain(view)
        self.assertIn("Map", plain_v)
        # seed hearth has an east (or similar) exit toward gallery
        self.assertTrue(
            "├─" in view or "└─" in view,
            msg=view,
        )
        # link type markup present in raw
        self.assertTrue(
            "spatial" in view.lower()
            or "temporal" in view.lower()
            or "narrative" in view.lower()
            or "dimensional" in view.lower(),
            msg=view,
        )

    def test_depth_cap(self) -> None:
        loc = self.world.player_location()
        assert loc is not None
        tree = collect_map_tree(self.world, loc.id, depth=99)
        self.assertEqual(tree.depth, MAX_MAP_DEPTH)


class MapDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_map_command_seed(self) -> None:
        r = dispatch(self.world, "map")
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Map", text)
        self.assertIn("here", text.lower())
        # should list at least one exit label from story seed
        raw = r.message
        self.assertTrue("├─" in raw or "└─" in raw or "No paths" in text)

    def test_map_depth_1(self) -> None:
        r = dispatch(self.world, "map 1")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("depth 1", plain(r.message).lower())

    def test_map_after_go(self) -> None:
        # walk east if possible, map still works
        exits = plain(dispatch(self.world, "exits").message)
        if "east" in exits.lower() or "gallery" in exits.lower():
            # try go along first listed - use go east as seed convention
            dispatch(self.world, "go east")
        r = dispatch(self.world, "map 1")
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Map", plain(r.message))

    def test_map_bad_args(self) -> None:
        r = dispatch(self.world, "map banana")
        self.assertTrue(r.ok)
        self.assertIn("Usage", plain(r.message))

    def test_help_map(self) -> None:
        r = dispatch(self.world, "help map")
        self.assertTrue(r.ok)
        text = plain(r.message).lower()
        self.assertIn("map", text)
        self.assertIn("depth", text)


if __name__ == "__main__":
    unittest.main()
