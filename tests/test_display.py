"""Player-facing display_name and kind-colored entity names (shipped helpers)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import (
    bullet,
    colored_name,
    kind_color,
    kind_label,
    plain,
    show_name,
)
from digital_office_spaces.ids import cute_name, display_name, is_cute_name
from digital_office_spaces.seed import seed_world_classic, seed_world_story
from digital_office_spaces.world import World


class DisplayNameUnitTests(unittest.TestCase):
    def test_cute_to_plain(self) -> None:
        self.assertEqual(display_name("QUIET-INVITATION"), "Quiet Invitation")
        self.assertEqual(display_name("SILVER-THREAD"), "Silver Thread")
        self.assertEqual(display_name("PRIME"), "Prime")
        self.assertEqual(
            display_name("THE-CATHEDRAL-OF-ORDINARY-LIGHT"),
            "The Cathedral Of Ordinary Light",
        )

    def test_already_plain_unchanged(self) -> None:
        self.assertEqual(display_name("Quiet Invitation"), "Quiet Invitation")
        self.assertEqual(display_name("half-written note"), "half-written note")

    def test_rich_instance_titles_preserved(self) -> None:
        self.assertEqual(display_name("Terminal-Prolog"), "Terminal-Prolog")
        self.assertEqual(
            display_name("Field Notes / Vol.1"), "Field Notes / Vol.1"
        )
        self.assertEqual(display_name("NOTES/Draft"), "NOTES/Draft")

    def test_storage_still_cute(self) -> None:
        self.assertEqual(cute_name("Quiet Invitation"), "QUIET-INVITATION")
        self.assertTrue(is_cute_name("QUIET-INVITATION"))


class ColoredNameUnitTests(unittest.TestCase):
    def test_place_location_not_purple_family(self) -> None:
        color = kind_color("place")
        low = color.lower()
        for bad in ("purple", "magenta", "orchid"):
            self.assertNotIn(bad, low, msg=f"place color still hard-to-read: {color!r}")
        # readable bright/light family preferred
        self.assertTrue(
            any(x in low for x in ("white", "yellow", "green", "cyan", "blue")),
            msg=f"unexpected place color {color!r}",
        )
        # but not purple-ish blue-only if we switched to white — white is fine
        cn = colored_name("THE-HEARTH-OF-UNFINISHED-MAPS", "place")
        self.assertIn(f"[{color}]", cn)
        self.assertEqual(plain(cn), "The Hearth Of Unfinished Maps")  # cute → title

    def test_person_uses_yellow_sense_uses_magenta(self) -> None:
        # person stays yellow-family; sense (ex-feeling) is magenta
        self.assertIn("yellow", kind_color("person").lower())
        self.assertIn("magenta", kind_color("sense").lower())
        cn = colored_name("EXAMPLE-NAME", "person")
        self.assertIn(f"[{kind_color('person')}]", cn)

    def test_colored_name_wraps_entity_not_kind_word(self) -> None:
        cn = colored_name("WOVEN", "realm")
        self.assertIn(f"[{kind_color('realm')}]", cn)
        self.assertIn("Woven", cn)
        self.assertNotIn("realm", cn)  # kind token is not inside colored_name
        self.assertEqual(plain(cn), "Woven")

        kl = kind_label("realm")
        self.assertIn("[dim]", kl)
        self.assertIn("realm", kl)
        # kind label is dim, not the realm color
        self.assertNotIn(f"[{kind_color('realm')}]", kl)

    def test_bullet_colors_name_dims_kind(self) -> None:
        row = bullet("QUIET-INVITATION", kind="sense")
        feel_color = kind_color("sense")
        self.assertIn(f"[{feel_color}]", row)
        self.assertIn("Quiet Invitation", row)
        # kind word present but dim, not kind-colored
        self.assertIn("[dim]sense[/dim]", row)
        # name is wrapped with sense color
        self.assertIn(f"[{feel_color}]Quiet Invitation[/{feel_color}]", row)

    def test_show_name_escapes_and_displays(self) -> None:
        self.assertEqual(plain(show_name("QUIET-INVITATION")), "Quiet Invitation")
        self.assertIn("[", show_name("x [y]"))  # escaped markup path still safe


class LookDisplaySmokeTests(unittest.TestCase):
    def test_classic_look_shows_plain_names_and_kinds(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_classic(conn)
        world = World(conn)
        result = dispatch(world, "look")
        self.assertTrue(result.ok)
        text = plain(result.message)
        self.assertIn("The Cathedral of Ordinary Light", text)
        self.assertNotIn("THE-CATHEDRAL-OF-ORDINARY-LIGHT", text)
        self.assertIn("Silver Thread", text)
        self.assertNotIn("SILVER-THREAD", text)
        # Presence: prime · name · short ref (no kind/subtype columns)
        self.assertRegex(text, r"THG-\d{3}-\d{4}")
        self.assertRegex(text, r"SNS-\d{3}-\d{4}")
        mat = kind_color("thing")
        self.assertIn(f"[{mat}]Silver Thread[/{mat}]", result.message)

    def test_story_look_colors_instance_names(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_story(conn)
        world = World(conn)
        result = dispatch(world, "look")
        text = plain(result.message)
        self.assertIn("The Hearth of Unfinished Maps", text)
        self.assertIn("Quiet Invitation", text)
        self.assertNotIn("QUIET-INVITATION", text)
        self.assertRegex(text, r"SNS-\d{3}-\d{4}")
        feel = kind_color("sense")
        realm = kind_color("realm")
        place = kind_color("place")
        self.assertIn(f"[{feel}]Quiet Invitation[/{feel}]", result.message)
        self.assertIn(f"[{realm}]Woven[/{realm}]", result.message)
        # place title uses bold + place color
        self.assertIn(f"[bold {place}]", result.message)
        self.assertNotIn(f"[{realm}]realm[/{realm}]", result.message)

    def test_look_things_show_prime_ven_when_retitled(self) -> None:
        """Instance title + kind + source prime (spawn as …)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_story(conn)
        world = World(conn)
        self.assertTrue(
            dispatch(
                world, "create thing Video Game | Interactive work."
            ).ok
        )
        self.assertTrue(
            dispatch(
                world,
                "spawn video-game as Something Mattered Here: The Forgetting House",
            ).ok
        )
        result = dispatch(world, "look")
        self.assertTrue(result.ok, msg=result.message)
        text = plain(result.message)
        self.assertIn("Something Mattered Here: The Forgetting House", text)
        self.assertIn("Video Game", text)
        self.assertRegex(text, r"THG-\d{3}-\d{4}")
        # same-name instances still show prime + name + code
        self.assertIn("Unfinished Quill", text)

    def test_resolution_still_accepts_whole_token(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_classic(conn)
        world = World(conn)
        # whole token "silver" still hits "Silver Thread"
        r = dispatch(world, "take silver")
        self.assertTrue(r.ok)
        inv_r = dispatch(world, "inv")
        inv = plain(inv_r.message)
        self.assertIn("Silver Thread", inv)
        self.assertIn("thing", inv)
        mat = kind_color("thing")
        self.assertIn(f"[{mat}]Silver Thread[/{mat}]", inv_r.message)


if __name__ == "__main__":
    unittest.main()
