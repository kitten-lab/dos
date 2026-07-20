"""Story-center seed: hearth start, lovers, shatter far away."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world, seed_world_story
from digital_office_spaces.world import World


def _story_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class StorySeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _story_world()

    def test_default_seed_world_is_story(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world(conn)
        w = World(conn)
        loc = w.player_location()
        assert loc is not None
        self.assertIn("HEARTH", loc.name.upper())

    def test_start_at_hearth_not_shatter(self) -> None:
        r = dispatch(self.world, "look")
        text = plain(r.message)
        self.assertIn("The Hearth of Unfinished Maps", text)
        self.assertNotIn("Shattered", text)
        self.assertNotIn("cracked mirror", text.lower())

    def test_lovers_and_stories_reachable(self) -> None:
        dispatch(self.world, "go along the story road")
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Twin Overlook", look)
        self.assertIn("Cartographer", look)

        dispatch(self.world, "go a generation later")
        look2 = plain(dispatch(self.world, "look").message)
        self.assertIn("Echo", look2)
        self.assertIn("Keeper", look2)

    def test_shatter_is_side_path(self) -> None:
        # hearth -> hall -> far archive -> shattered
        dispatch(self.world, "go into the living shelves")
        dispatch(self.world, "go deeper into the side wing")
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Far Archive", look)
        dispatch(self.world, "go years after the break")
        look2 = plain(dispatch(self.world, "look").message)
        self.assertIn("Shattered", look2)


if __name__ == "__main__":
    unittest.main()
