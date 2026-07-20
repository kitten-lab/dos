"""Nano-like << / <<studio editor: commit path + text revision log."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_office_spaces.commands import dispatch
from digital_office_spaces.db import connect
from digital_office_spaces.format import plain
from digital_office_spaces.multiline_open import (
    commit_multiline_session,
    parse_multiline_opener,
    seed_initial_body,
)
from wbs_seed_fixtures import seed_world_story
from digital_office_spaces.studio_text import is_studio
from digital_office_spaces.text_editor import (
    _editor_hint_markup,
    _preview_markup,
    set_editor_hook,
    word_bounds_at,
)
from digital_office_spaces.world import World


class WordBoundsTests(unittest.TestCase):
    def test_word_under_cursor(self) -> None:
        line = "hello castaways world"
        # on 'c' of castaways
        self.assertEqual(word_bounds_at(line, 6), (6, 15))
        # just after word (cursor after 's')
        self.assertEqual(word_bounds_at(line, 15), (6, 15))
        # first word
        self.assertEqual(word_bounds_at(line, 0), (0, 5))
        # cursor on space *after* a word still selects that word (common editor UX)
        self.assertEqual(word_bounds_at(line, 5), (0, 5))
        # underscore / alnum
        self.assertEqual(word_bounds_at("soft_launch", 4), (0, 11))
        # pure whitespace / empty → none
        self.assertIsNone(word_bounds_at("", 0))
        self.assertIsNone(word_bounds_at("   ", 1))
        self.assertIsNone(word_bounds_at("  between  ", 1))


class PreviewMarkupTests(unittest.TestCase):
    def test_empty_buffer_message(self) -> None:
        self.assertIn("empty", _preview_markup("", studio=True).lower())
        self.assertIn("empty", _preview_markup("   ", studio=False).lower())

    def test_plain_escapes_markup_brackets(self) -> None:
        out = _preview_markup("a [b] c", studio=False)
        # plain path uses safe() so raw [tags] are escaped for Rich
        self.assertIn(r"\[b]", out)

    def test_studio_renders_bold(self) -> None:
        out = _preview_markup("**hello** world", studio=True)
        self.assertIn("bold", out.lower())
        self.assertIn("hello", out)

    def test_hint_shows_preview_mode(self) -> None:
        edit = _editor_hint_markup("t", studio=True, preview=False)
        prev = _editor_hint_markup("t", studio=True, preview=True)
        self.assertIn("EDIT", edit)
        self.assertIn("PREVIEW", prev)
        self.assertIn("F2", edit)
        self.assertIn("preview", edit.lower())


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class ParseOpenerTests(unittest.TestCase):
    def test_desc_book_lore_openers(self) -> None:
        d = parse_multiline_opener("@desc <<studio")
        assert d is not None
        self.assertEqual(d.kind, "desc")
        self.assertTrue(d.studio)

        d2 = parse_multiline_opener("@desc on quill <<")
        assert d2 is not None
        self.assertEqual(d2.desc_rest, "on quill")
        self.assertFalse(d2.studio)

        b = parse_multiline_opener("book page add notes Intro <<studio")
        assert b is not None
        self.assertEqual(b.kind, "book_page")

        l = parse_multiline_opener("lore add Founding <<studio")
        assert l is not None
        self.assertEqual(l.kind, "lore")
        self.assertEqual(l.lore_title, "Founding")

        self.assertIsNone(parse_multiline_opener("look"))
        self.assertIsNone(parse_multiline_opener("lore add from notes 1:2"))


class EditorCommitAndLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        set_editor_hook(None)

    def tearDown(self) -> None:
        set_editor_hook(None)

    def test_desc_editor_save_and_revision_restore(self) -> None:
        ml = parse_multiline_opener("@desc <<studio")
        assert ml is not None
        body1 = "First save line.\nSecond."
        r = commit_multiline_session(self.world, ml, body1)
        self.assertTrue(r.ok, msg=r.message)
        loc = self.world.player_location()
        assert loc is not None
        self.assertTrue(is_studio(loc.description))
        self.assertIn("First save", loc.description or "")

        revs = self.world.list_text_revisions(
            "instance", loc.id, field="description"
        )
        self.assertEqual(len(revs), 1)
        rid1 = revs[0]["id"]

        r = commit_multiline_session(self.world, ml, "Second save only.")
        self.assertTrue(r.ok)
        revs = self.world.list_text_revisions(
            "instance", loc.id, field="description"
        )
        self.assertEqual(len(revs), 2)

        log = plain(dispatch(self.world, "text log").message)
        self.assertIn("Text log", log)
        self.assertGreaterEqual(log.count("trev_"), 1)
        # Newest revision body is second save
        revs = self.world.list_text_revisions(
            "instance", loc.id, field="description"
        )
        self.assertIn("Second save", revs[0]["body"])

        restored = dispatch(self.world, f"text restore {rid1}")
        self.assertTrue(restored.ok, msg=restored.message)
        loc2 = self.world.player_location()
        assert loc2 is not None
        self.assertIn("First save", loc2.description or "")

        show = plain(dispatch(self.world, f"text show {rid1}").message)
        self.assertIn("First save", show)

    def test_book_page_editor_save(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create book Field Notes | nb.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn field-notes").ok)
        ml = parse_multiline_opener(
            "book page add field-notes Preface <<studio"
        )
        assert ml is not None
        r = commit_multiline_session(
            self.world, ml, "# Title\n\n**Hello** body."
        )
        self.assertTrue(r.ok, msg=r.message)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        pages = self.world.list_book_pages(book.id)
        self.assertEqual(len(pages), 1)
        self.assertTrue(is_studio(pages[0]["body"]))
        revs = self.world.list_text_revisions(
            "book_page", pages[0]["id"], field="body"
        )
        self.assertEqual(len(revs), 1)

        log = plain(
            dispatch(self.world, "text log book field-notes page 1").message
        )
        self.assertIn("Text log", log)

        # edit path prefill + second save
        ml2 = parse_multiline_opener("book page edit field-notes 1 <<studio")
        assert ml2 is not None
        initial = seed_initial_body(self.world, ml2)
        self.assertIn("Hello", initial)
        r2 = commit_multiline_session(self.world, ml2, "Rewritten only.")
        self.assertTrue(r2.ok, msg=r2.message)
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertIn("Rewritten", body)

    def test_lore_editor_save(self) -> None:
        ml = parse_multiline_opener("lore add Origin <<studio")
        assert ml is not None
        r = commit_multiline_session(
            self.world, ml, "Long lore\nspanning lines."
        )
        self.assertTrue(r.ok, msg=r.message)
        listed = plain(dispatch(self.world, "lore").message)
        self.assertIn("Origin", listed)
        self.assertIn("Long lore", listed)
        loc = self.world.player_location()
        assert loc is not None
        revs = self.world.list_text_revisions(
            "instance", loc.id, field="lore_body"
        )
        self.assertGreaterEqual(len(revs), 1)
        log = plain(dispatch(self.world, "text log lore").message)
        self.assertIn("lore", log.lower())

    def test_editor_hook_used_by_run_text_editor(self) -> None:
        from digital_office_spaces.text_editor import StudioBufferResult, run_text_editor

        set_editor_hook(lambda i, t, s: "hooked body")
        out = run_text_editor(initial="x", title="t")
        assert isinstance(out, StudioBufferResult)
        self.assertEqual(out.body, "hooked body")
        set_editor_hook(lambda i, t, s: None)
        self.assertIsNone(run_text_editor(initial="x", title="t"))

    def test_book_page_edit_saves_title_and_body(self) -> None:
        """Single-page editor chrome: page_title applied on book page edit commit."""
        self.assertTrue(
            dispatch(self.world, "create book Field Notes | nb.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn field-notes").ok)
        add = dispatch(
            self.world, "book page add field-notes Old Title | original body"
        )
        self.assertTrue(add.ok, msg=add.message)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        page = self.world.list_book_pages(book.id)[0]
        self.assertEqual(page["title"], "Old Title")

        ml = parse_multiline_opener(
            f"book page edit field-notes {page['position']} <<studio"
        )
        assert ml is not None
        from digital_office_spaces.multiline_open import seed_page_title

        seeded = seed_page_title(self.world, ml)
        self.assertEqual(seeded, "Old Title")

        r = commit_multiline_session(
            self.world,
            ml,
            "new body line",
            page_title="New Title",
        )
        self.assertTrue(r.ok, msg=r.message)
        page2 = self.world.list_book_pages(book.id)[0]
        self.assertEqual(page2["title"], "New Title")
        self.assertIn("new body line", page2["body"] or "")

    def test_cli_wires_parse_and_editor(self) -> None:
        import inspect

        from digital_office_spaces import cli

        src = inspect.getsource(cli)
        self.assertIn("parse_multiline_opener", src)
        self.assertIn("run_text_editor", src)
        self.assertIn("make_studio_buffer_screen", src)
        self.assertIn("commit_multiline_session", src)


if __name__ == "__main__":
    unittest.main()
