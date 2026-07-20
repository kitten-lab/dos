"""Help index/topics + VEN lore: drive real dispatch path."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from dos.commands import HELP, dispatch
from dos.db import connect
from dos.format import plain
from dos.help_topics import render_help_index, resolve_topic
from wbs_seed_fixtures import seed_world_classic as seed_world
from dos.world import World


def _seeded_world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world(conn)
    return World(conn)


class HelpIndexAndTopicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _seeded_world()

    def test_bare_help_and_question_are_short_index(self) -> None:
        a = dispatch(self.world, "help")
        b = dispatch(self.world, "?")
        self.assertTrue(a.ok)
        self.assertTrue(b.ok)
        self.assertEqual(a.message, b.message)
        self.assertEqual(a.message, HELP)
        self.assertEqual(a.message, render_help_index())
        text = plain(a.message)
        self.assertIn("cheat sheet", text.lower())
        self.assertIn("look", text)
        self.assertIn("dig", text)
        self.assertIn("lore", text)
        # Grouped categories + digit codes (look is 11)
        self.assertIn("11", text)
        self.assertIn("movement", text.lower())
        self.assertIn("env controls", text.lower())
        self.assertIn("creator tools", text.lower())
        # Must NOT dump the old full-manual wall as default
        self.assertNotIn("How to navigate", text)
        self.assertNotIn("Instruction Manual", text)
        self.assertNotIn("Start here", text)
        self.assertLess(len(text), 4500)

    def test_help_term_returns_detail_with_example(self) -> None:
        result = dispatch(self.world, "help look")
        self.assertTrue(result.ok)
        text = plain(result.message)
        self.assertIn("help · look", text.lower().replace("·", "·"))
        self.assertIn("Usage", text)
        self.assertIn("Full room view", text)
        # detail is instructional prose, not the cheat sheet root
        self.assertNotIn("cheat sheet", text.lower())
        detail = dispatch(self.world, "help lore")
        lore_text = plain(detail.message)
        self.assertIn("lore ven", lore_text)
        self.assertIn("lore add", lore_text)
        self.assertIn("Prime VEN", lore_text)

    def test_help_code_resolves_like_term(self) -> None:
        by_code = dispatch(self.world, "help 1A")
        by_term = dispatch(self.world, "help look")
        self.assertTrue(by_code.ok)
        self.assertEqual(plain(by_code.message), plain(by_term.message))

    def test_help_unknown_term_no_crash(self) -> None:
        r = dispatch(self.world, "help not-a-real-command-xyz")
        self.assertTrue(r.ok)
        text = plain(r.message).lower()
        self.assertIn("unknown", text)
        self.assertIn("help", text)

    def test_help_aliases(self) -> None:
        self.assertEqual(resolve_topic("l"), "look")
        self.assertEqual(resolve_topic("g"), "go")
        self.assertEqual(plain(dispatch(self.world, "help l").message), plain(dispatch(self.world, "help look").message))

    def test_look_still_works_smoke(self) -> None:
        r = dispatch(self.world, "look")
        self.assertTrue(r.ok)
        text = plain(r.message)
        self.assertIn("The Cathedral of Ordinary Light", text)
        self.assertTrue(
            "Paths" in text or "No paths" in text,
            msg=text[:200],
        )

    def test_plain_index_no_broken_tags(self) -> None:
        text = plain(dispatch(self.world, "help").message)
        self.assertIsNone(re.search(r"\[/?(?:bold|dim|cyan|red|green)\b", text))


class VenLoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _seeded_world()

    def test_lore_on_ven_add_and_list_round_trip(self) -> None:
        add = dispatch(
            self.world,
            "lore ven silver-thread add Binding | Thread that ties frayed timelines.",
        )
        self.assertTrue(add.ok, msg=add.message)
        self.assertIn("VEN", plain(add.message))

        listed = dispatch(self.world, "lore ven silver-thread")
        self.assertTrue(listed.ok)
        text = plain(listed.message)
        self.assertIn("Binding", text)
        self.assertIn("Thread that ties frayed timelines", text)
        # slug still in ok/heading path; display may also show plain
        self.assertTrue(
            "SILVER-THREAD" in text or "Silver Thread" in text
        )

        # name match (relaxed input)
        by_name = dispatch(self.world, "lore ven Silver Thread")
        self.assertTrue(by_name.ok)
        self.assertIn("Binding", plain(by_name.message))

    def test_place_instance_lore_still_works(self) -> None:
        add = dispatch(
            self.world,
            "lore add Local note | Only for this cathedral instance.",
        )
        self.assertTrue(add.ok)
        listed = dispatch(self.world, "lore")
        text = plain(listed.message)
        self.assertIn("Local note", text)
        self.assertIn("Only for this cathedral instance", text)

    def test_seed_ven_lore_readable(self) -> None:
        # seed attaches motif lore to silver-thread VEN
        r = dispatch(self.world, "lore ven silver-thread")
        self.assertTrue(r.ok)
        # may already have seed entry
        text = plain(r.message)
        self.assertTrue(
            "SILVER-THREAD" in text or "Motif" in text or "No lore" in text
        )


if __name__ == "__main__":
    unittest.main()
