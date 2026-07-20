"""Live line echo + last-line undo during multiline @desc collection."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from digital_office_spaces import cli
from digital_office_spaces.cli import (
    MultilineDescDraft,
    _collect_multiline_desc,
    _desc_collect_hint,
)
from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.seed import seed_world_story
from digital_office_spaces.studio_text import FORMAT_HEADER, is_studio
from digital_office_spaces.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class MultilineDescDraftTests(unittest.TestCase):
    def test_accept_undo_done_sequence(self) -> None:
        d = MultilineDescDraft()
        self.assertEqual(d.feed("line A"), "accepted")
        self.assertEqual(d.feed("line B"), "accepted")
        self.assertEqual(d.lines, ["line A", "line B"])
        self.assertEqual(d.feed("undo"), "undone")
        self.assertEqual(d.lines, ["line A"])
        self.assertEqual(d.feed("u"), "undone")
        self.assertEqual(d.lines, [])
        self.assertEqual(d.feed("undo"), "empty_undo")

        d2 = MultilineDescDraft()
        d2.feed("A")
        d2.feed("B")
        self.assertEqual(d2.feed("/undo"), "undone")
        self.assertEqual(d2.lines, ["A"])
        d2.feed("C")
        self.assertEqual(d2.feed("."), "done")
        self.assertEqual(d2.body(), "A\nC")

    def test_cancel_on_end_when_empty(self) -> None:
        d = MultilineDescDraft()
        self.assertEqual(d.feed("."), "cancel")
        self.assertIsNone(d.body())

    def test_end_markers(self) -> None:
        for end in (".", ">>", "}"):
            d = MultilineDescDraft()
            d.feed("x")
            self.assertEqual(d.feed(end), "done")
            self.assertEqual(d.body(), "x")


class CollectMultilineDescTests(unittest.TestCase):
    def test_scripted_read_line_echo_and_undo(self) -> None:
        inputs = iter(
            [
                "line A",
                "line B",
                "undo",
                "line C",
                ".",
            ]
        )
        accepted: list[str] = []
        undos: list[int] = []

        def on_accepted(line: str, draft: MultilineDescDraft) -> None:
            accepted.append(line)

        def on_undone(draft: MultilineDescDraft) -> None:
            undos.append(len(draft))

        body = _collect_multiline_desc(
            lambda: next(inputs),
            on_accepted=on_accepted,
            on_undone=on_undone,
        )
        self.assertEqual(body, "line A\nline C")
        self.assertEqual(accepted, ["line A", "line B", "line C"])
        self.assertEqual(undos, [1])  # after undo, 1 line left
        # on_accepted called once per accepted content line
        self.assertEqual(len(accepted), 3)

    def test_collect_empty_cancel(self) -> None:
        body = _collect_multiline_desc(lambda: ".")
        self.assertIsNone(body)

    def test_hint_mentions_undo_and_echo(self) -> None:
        h = _desc_collect_hint(studio=True)
        self.assertIn("studio", h.lower())
        self.assertIn("undo", h.lower())
        self.assertIn("shown", h.lower() or "line" in h.lower())


class DescLiveIntegrationTests(unittest.TestCase):
    def test_studio_dispatch_after_collect_sim(self) -> None:
        """Draft A, B, undo, C → commit via real @desc studio path."""
        world = _world()
        inputs = iter(["# Title", "**bold**", "u", "plain tail", "."])
        accepted: list[str] = []
        body = _collect_multiline_desc(
            lambda: next(inputs),
            on_accepted=lambda ln, d: accepted.append(ln),
            on_undone=lambda d: None,
        )
        self.assertEqual(body, "# Title\nplain tail")
        self.assertEqual(accepted, ["# Title", "**bold**", "plain tail"])
        r = dispatch(world, f"@desc studio | {body}")
        self.assertTrue(r.ok, msg=r.message)
        loc = world.player_location()
        assert loc is not None
        ov = world.get_description_override(loc.id)
        assert ov is not None
        self.assertTrue(is_studio(ov) or ov.startswith(FORMAT_HEADER))
        self.assertIn("Title", ov)
        self.assertIn("plain tail", ov)
        self.assertNotIn("**bold**", ov)

    def test_cli_wires_buffer_editor(self) -> None:
        """<< / <<studio open the nano-like editor (not line-at-a-time draft)."""
        src = inspect.getsource(cli)
        self.assertIn("parse_multiline_opener", src)
        self.assertIn("commit_multiline_session", src)
        self.assertIn("run_text_editor", src)
        self.assertIn("make_studio_buffer_screen", src)
        self.assertIn("Ctrl+S", src)
        # Draft helper still exists for unit tests / legacy
        self.assertIn("MultilineDescDraft", src)
        from digital_office_spaces import text_editor

        te = inspect.getsource(text_editor)
        self.assertIn("ctrl+a", te)
        self.assertIn("select_all", te)


if __name__ == "__main__":
    unittest.main()
