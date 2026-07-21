"""Book VEN: pages, lines, reader layout, status colors."""

from __future__ import annotations

import inspect
import re
import tempfile
import unittest
from pathlib import Path

from dos import cli
from dos.book import (
    PAGE_VIEW_WIDTH,
    STATUS_COLORS,
    format_numbered_lines,
    format_page_view,
    format_status_markup,
    gutter_prefix_width,
    insert_page_lines,
    move_page_line,
    page_index_after_nav,
    remove_page_line,
    resolve_book_status,
    split_page_lines,
    wrap_text_hanging,
)
from dos.studio_text import FORMAT_HEADER, is_studio, with_studio_header
from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from wbs_seed_fixtures import seed_world_story
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class PageNavHelperTests(unittest.TestCase):
    def test_clamp_prev_next(self) -> None:
        self.assertEqual(page_index_after_nav(0, -1, 3), 0)
        self.assertEqual(page_index_after_nav(0, 1, 3), 1)
        self.assertEqual(page_index_after_nav(2, 1, 3), 2)
        self.assertEqual(page_index_after_nav(1, -1, 3), 0)
        self.assertEqual(page_index_after_nav(0, 1, 0), 0)


class PageLineUnitTests(unittest.TestCase):
    def test_split_and_number_format_dim(self) -> None:
        body = "Alpha\nBeta\nGamma"
        self.assertEqual(split_page_lines(body), ["Alpha", "Beta", "Gamma"])
        numbered = format_numbered_lines(body)
        self.assertIn("[dim]", numbered)
        self.assertIn("[/dim]", numbered)
        self.assertIn("Alpha", numbered)
        plain_n = plain(numbered)
        self.assertIn("1  Alpha", plain_n)
        self.assertIn("2  Beta", plain_n)

    def test_insert_begin_middle_end(self) -> None:
        body = "mid"
        body = insert_page_lines(body, 1, "start")
        self.assertEqual(split_page_lines(body), ["start", "mid"])
        body = insert_page_lines(body, 2, "between")
        self.assertEqual(split_page_lines(body), ["start", "between", "mid"])
        body = insert_page_lines(body, 4, "end")
        self.assertEqual(split_page_lines(body), ["start", "between", "mid", "end"])

    def test_insert_multi_paragraph(self) -> None:
        body = insert_page_lines("only", 1, "a\nb")
        self.assertEqual(split_page_lines(body), ["a", "b", "only"])

    def test_remove_and_move(self) -> None:
        body = "A\nB\nC\nD"
        body = remove_page_line(body, 2)
        self.assertEqual(split_page_lines(body), ["A", "C", "D"])
        body = move_page_line(body, 3, 1)
        self.assertEqual(split_page_lines(body), ["D", "A", "C"])
        body = move_page_line(body, 1, 3)
        self.assertEqual(split_page_lines(body), ["A", "C", "D"])

    def test_studio_body_keeps_logical_line_numbers(self) -> None:
        body = with_studio_header(
            "# Title\n\n**Bold** words that would soft-wrap in a narrow terminal "
            "still count as one logical line only.\n---\nTail"
        )
        numbered = format_numbered_lines(body)
        plain_n = plain(numbered)
        # logical lines numbered 1..n (blank between title and body unnumbered)
        self.assertIn("1", plain_n)
        self.assertIn("Title", plain_n)
        self.assertIn("Bold", plain_n)
        self.assertIn("Tail", plain_n)
        # bold rendered, not raw stars in plain capture of studio
        self.assertNotIn("**Bold**", plain_n)
        # content lines still dim-numbered (blank does not add a number)
        self.assertGreaterEqual(numbered.count("[dim]"), 3)

    def test_blank_lines_have_no_gutter_number(self) -> None:
        """Empty space is unnumbered; next content keeps its logical index."""
        body = "Alpha\n\nGamma"
        plain_n = plain(format_numbered_lines(body))
        self.assertRegex(plain_n, r"(?m)^\s*1\s+Alpha")
        self.assertRegex(plain_n, r"(?m)^\s*3\s+Gamma")
        self.assertNotRegex(plain_n, r"(?m)^\s*2\s*$")
        self.assertNotRegex(plain_n, r"(?m)^\s*2\s+")

        studio = with_studio_header("One\n\nTwo")
        plain_s = plain(format_numbered_lines(studio))
        self.assertRegex(plain_s, r"(?m)^\s*1\s+One")
        self.assertRegex(plain_s, r"(?m)^\s*3\s+Two")
        self.assertNotRegex(plain_s, r"(?m)^\s*2\s+")

    def test_fence_box_line_numbers_skip_padding(self) -> None:
        """Pad rows inside a code box are unnumbered; body lines stay sequential."""
        from dos.studio_text import prepare_stored_text

        bt = "```"
        body = prepare_stored_text(
            f"before\n{bt}\nA\nB\n{bt}\nafter",
            studio=True,
        )
        plain_n = plain(format_numbered_lines(body))
        # Source: 1 before, 2 open, 3 A, 4 B, 5 close, 6 after
        self.assertRegex(plain_n, r"(?m)^\s*1\s+before")
        self.assertRegex(plain_n, r"(?m)^\s*2\s+┌")
        self.assertRegex(plain_n, r"(?m)^\s*3\s+│ A")
        self.assertRegex(plain_n, r"(?m)^\s*4\s+│ B")
        self.assertRegex(plain_n, r"(?m)^\s*5\s+└")
        self.assertRegex(plain_n, r"(?m)^\s*6\s+after")
        # No number 7 invented; no jump that leaves B unnumbered
        self.assertNotRegex(plain_n, r"(?m)^\s*7\s+")
        # Pad rows: hang-indent only (spaces, then │)
        padish = [
            ln
            for ln in plain_n.splitlines()
            if "│" in ln and re.match(r"^\s+│", ln)
        ]
        self.assertGreaterEqual(len(padish), 2, msg=plain_n)

    def test_long_line_hangs_indent_past_gutter(self) -> None:
        """Wrapped logical lines indent past the line-number gutter (no extra numbers)."""
        # Force wrap: view width 40, gutter "1  " = 4 cols → content ~36
        long = (
            "word " * 20
        ).strip()  # far longer than content width
        body = f"{long}\nShort."
        numbered = format_numbered_lines(body, view_width=PAGE_VIEW_WIDTH)
        plain_n = plain(numbered)
        lines = [ln for ln in plain_n.splitlines() if ln.strip() or ln.startswith(" ")]
        # One logical line number "1" for the long unit
        num_lines = [ln for ln in plain_n.splitlines() if re.match(r"^\s*1\s+", ln)]
        self.assertEqual(len(num_lines), 1, msg=plain_n)
        # Line 2 is still its own number
        self.assertRegex(plain_n, r"(?m)^\s*2\s+Short\.")
        # Continuations: start with spaces equal to gutter width, no leading digit
        hang = gutter_prefix_width(2)  # max(2, len("2")) with 2 lines
        cont = [
            ln
            for ln in plain_n.splitlines()
            if ln.startswith(" " * hang) and not re.match(r"^\s*\d", ln.lstrip()[:1] or "")
        ]
        # At least one hang-indented continuation row
        cont2 = [ln for ln in plain_n.splitlines() if ln.startswith(" " * hang)]
        self.assertGreaterEqual(len(cont2), 1, msg=plain_n)
        for ln in cont2:
            # Must not look like a new numbered line
            self.assertFalse(re.match(r"^\s*\d+\s+\S", ln), msg=ln)
            self.assertTrue(ln[:hang] == " " * hang, msg=repr(ln[: hang + 5]))
        # Short line still classic shape
        self.assertIn("2  Short.", plain_n)
        # No broken Rich tags in plain capture of markup source
        self.assertIsNone(re.search(r"\[/?(?:dim|bold)\b", plain_n))
        # page view path uses same formatter
        view = format_page_view(
            book_name="Notes",
            status="complete",
            page_index=0,
            page_count=1,
            title="Long",
            body=long,
            width=PAGE_VIEW_WIDTH,
        )
        vplain = plain(view)
        self.assertRegex(vplain, r"(?m)^\s*1\s+")
        hang_rows = [ln for ln in vplain.splitlines() if ln.startswith(" " * hang)]
        self.assertGreaterEqual(len(hang_rows), 1, msg=vplain)

    def test_studio_long_line_hangs_same_way(self) -> None:
        long = ("alpha " * 18).strip()
        body = with_studio_header(f"**Bold** start {long}\nTail end.")
        numbered = format_numbered_lines(body, view_width=PAGE_VIEW_WIDTH)
        plain_n = plain(numbered)
        # one number for first logical line
        self.assertEqual(
            len(re.findall(r"(?m)^\s*1\s+", plain_n)),
            1,
            msg=plain_n,
        )
        hang = gutter_prefix_width(2)
        self.assertTrue(
            any(ln.startswith(" " * hang) for ln in plain_n.splitlines()),
            msg=plain_n,
        )
        self.assertIn("Tail end", plain_n)
        self.assertNotIn("**Bold**", plain_n)

    def test_wrap_text_hanging_units(self) -> None:
        segs = wrap_text_hanging("one two three four", 10)
        self.assertTrue(all(len(s) <= 10 for s in segs))
        self.assertEqual(" ".join(segs).replace("  ", " "), "one two three four")

    def test_wrap_does_not_split_markdown_links(self) -> None:
        """Book hang-wrap must keep [label](https://…) intact for Studio render."""
        link = "[docs](https://example.com/very/long/path/to/resource)"
        prose = f"See {link} for more about the office tools and calendars."
        segs = wrap_text_hanging(prose, 28)
        joined = " ".join(segs)
        self.assertIn(link, joined)
        # No segment should contain only a partial link (half the markdown)
        for seg in segs:
            if "http" in seg or "](" in seg or seg.startswith("["):
                self.assertIn(link, seg, msg=segs)

    def test_numbered_studio_keeps_links_after_wrap(self) -> None:
        from dos.book import format_numbered_lines

        body = (
            ".format: studio\n"
            "Read [Handbook](https://example.com/office/handbook/full-guide) "
            "before onboarding."
        )
        view = format_numbered_lines(body, view_width=40)
        # Rendered click action (not broken source)
        self.assertIn("app.open_url", view)
        self.assertIn("Handbook", view)
        # Unrendered mid-break would leave raw "](https" fragments
        self.assertNotIn("](https", view)

    def test_format_page_view_layout(self) -> None:
        view = format_page_view(
            book_name="Notes",
            status="complete",
            page_index=0,
            page_count=2,
            title="Preface",
            body="One\nTwo",
        )
        # dim line numbers
        self.assertIn("[dim]", view)
        self.assertIn("One", view)
        # status color
        self.assertIn("[green]complete[/green]", view)
        # centered ALL-CAPS page title
        self.assertIn("PREFACE", view)
        self.assertNotIn("\nPreface\n", view)
        lines = view.split("\n")
        # chrome first line has book name + status, no page n/m
        self.assertIn("Notes", lines[0])
        self.assertIn("complete", lines[0])
        self.assertNotIn("page 1/2", lines[0])
        # blank separation after chrome
        self.assertEqual(lines[1], "")
        self.assertTrue(lines[2].startswith("-"))
        # title line centered
        title_line = next(ln for ln in lines if "PREFACE" in ln)
        self.assertTrue(title_line.strip() == "PREFACE" or title_line.index("P") > 0)
        pad = (PAGE_VIEW_WIDTH - len("PREFACE")) // 2
        self.assertEqual(title_line, (" " * pad) + "PREFACE")
        # footer only at bottom
        self.assertEqual(lines[-1], "page 1/2")
        self.assertNotIn("page 1/2", "\n".join(lines[:-1]))


class BookStatusTests(unittest.TestCase):
    def test_resolve_and_colors(self) -> None:
        self.assertEqual(resolve_book_status(page_count=0, incomplete=False), "empty")
        self.assertEqual(resolve_book_status(page_count=0, incomplete=True), "empty")
        self.assertEqual(resolve_book_status(page_count=1, incomplete=True), "incomplete")
        self.assertEqual(resolve_book_status(page_count=1, incomplete=False), "complete")
        self.assertEqual(STATUS_COLORS["empty"], "red")
        self.assertEqual(STATUS_COLORS["incomplete"], "yellow")
        self.assertEqual(STATUS_COLORS["complete"], "green")
        self.assertEqual(format_status_markup("empty"), "[red]empty[/red]")
        self.assertEqual(format_status_markup("incomplete"), "[yellow]incomplete[/yellow]")
        self.assertEqual(format_status_markup("complete"), "[green]complete[/green]")


class BookDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()
        r = dispatch(self.world, "create book Field Notes | Working notebook.")
        self.assertTrue(r.ok, msg=r.message)
        r = dispatch(self.world, "spawn field-notes")
        self.assertTrue(r.ok, msg=r.message)

    def test_new_book_empty_by_default(self) -> None:
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        self.assertEqual(self.world.book_status(book.id), "empty")
        opened = dispatch(self.world, "book open field-notes")
        self.assertTrue(opened.ok)
        raw = opened.message
        self.assertIn("[red]empty[/red]", raw)
        self.assertIn("empty", plain(raw).lower())
        listed = dispatch(self.world, "book pages field-notes").message
        self.assertIn("[red]empty[/red]", listed)

    def test_status_colors_incomplete_complete(self) -> None:
        dispatch(self.world, "book page add field-notes A | body")
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        self.assertEqual(self.world.book_status(book.id), "complete")
        raw = dispatch(self.world, "book open field-notes").message
        self.assertIn("[green]complete[/green]", raw)

        dispatch(self.world, "book incomplete field-notes")
        self.assertEqual(self.world.book_status(book.id), "incomplete")
        raw = dispatch(self.world, "book open field-notes").message
        self.assertIn("[yellow]incomplete[/yellow]", raw)

        dispatch(self.world, "book complete field-notes")
        self.assertEqual(self.world.book_status(book.id), "complete")
        raw = dispatch(self.world, "book open field-notes").message
        self.assertIn("[green]complete[/green]", raw)

    def test_add_pages_order_and_newlines(self) -> None:
        r = dispatch(
            self.world,
            r"book page add field-notes Preface | It begins.\nStill begins.",
        )
        self.assertTrue(r.ok, msg=r.message)
        r = dispatch(
            self.world,
            "book page add field-notes Chapter One | The road remembers.",
        )
        self.assertTrue(r.ok, msg=r.message)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        pages = self.world.list_book_pages(book.id)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["title"], "Preface")
        self.assertEqual(pages[0]["body"], "It begins.\nStill begins.")
        self.assertEqual(pages[0]["position"], 1)
        self.assertEqual(pages[1]["title"], "Chapter One")
        self.assertEqual(pages[1]["position"], 2)

        listed = plain(dispatch(self.world, "book pages field-notes").message)
        self.assertIn("Preface", listed)
        self.assertIn("Chapter One", listed)

    def test_insert_at_position(self) -> None:
        dispatch(self.world, "book page add field-notes A | first")
        dispatch(self.world, "book page add field-notes C | third")
        r = dispatch(
            self.world,
            "book page insert field-notes 2 B | second",
        )
        self.assertTrue(r.ok, msg=r.message)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        pages = self.world.list_book_pages(book.id)
        titles = [p["title"] for p in pages]
        bodies = [p["body"] for p in pages]
        self.assertEqual(titles, ["A", "B", "C"])
        self.assertEqual(bodies, ["first", "second", "third"])
        self.assertEqual([p["position"] for p in pages], [1, 2, 3])

    def test_incomplete_flag(self) -> None:
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        # no pages → empty, not incomplete, even before flag
        self.assertEqual(self.world.book_status(book.id), "empty")
        self.assertFalse(self.world.book_incomplete(book.id))
        dispatch(self.world, "book page add field-notes X | y")
        r = dispatch(self.world, "book incomplete field-notes")
        self.assertTrue(r.ok)
        self.assertTrue(self.world.book_incomplete(book.id))
        ex = plain(dispatch(self.world, "examine field-notes").message)
        self.assertIn("incomplete", ex.lower())
        dispatch(self.world, "book complete field-notes")
        self.assertFalse(self.world.book_incomplete(book.id))
        pages_msg = plain(dispatch(self.world, "book pages field-notes").message)
        self.assertIn("complete", pages_msg.lower())

    def test_open_returns_book_id_for_modal(self) -> None:
        dispatch(self.world, "book page add field-notes Only | hello")
        r = dispatch(self.world, "book open field-notes")
        self.assertTrue(r.ok)
        self.assertIsNotNone(r.open_book_id)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        self.assertEqual(r.open_book_id, book.id)
        self.assertIn("hello", plain(r.message))

    def test_open_shows_bible_style_line_numbers_and_layout(self) -> None:
        r = dispatch(
            self.world,
            r"book page add field-notes Verse | First line.\nSecond line.",
        )
        self.assertTrue(r.ok, msg=r.message)
        raw = dispatch(self.world, "book open field-notes").message
        self.assertIn("[dim]", raw)
        opened = plain(raw)
        self.assertIn("1  First line.", opened)
        self.assertIn("2  Second line.", opened)
        self.assertIn("VERSE", opened)
        self.assertTrue(opened.strip().endswith("page 1/1") or "page 1/1" in opened.splitlines()[-5:])
        # page counter not on first chrome line alone with body
        chrome = opened.splitlines()[0]
        self.assertNotIn("page 1/1", chrome)

    def test_studio_page_add_edit_and_open(self) -> None:
        r = dispatch(
            self.world,
            r"book page add field-notes Invocation | studio | # Call\n\n**Beloved** stranger.\n---\nEnd.",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("studio", plain(r.message).lower())
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        pages = self.world.list_book_pages(book.id)
        self.assertEqual(len(pages), 1)
        self.assertTrue(is_studio(pages[0]["body"]))
        self.assertTrue(pages[0]["body"].startswith(FORMAT_HEADER))

        opened = dispatch(self.world, "book open field-notes")
        text = plain(opened.message)
        self.assertIn("Call", text)
        self.assertIn("Beloved", text)
        self.assertIn("End", text)
        # light numbers present on logical lines
        self.assertRegex(text, r"1\s+")
        self.assertNotIn("**Beloved**", text)

        r = dispatch(
            self.world,
            r"book page edit field-notes 1 studio | # Rewritten\nOnly one more line.",
        )
        self.assertTrue(r.ok, msg=r.message)
        body2 = self.world.list_book_pages(book.id)[0]["body"]
        self.assertTrue(is_studio(body2))
        self.assertIn("Rewritten", body2)
        self.assertNotIn("Beloved", body2)

    def test_multiline_studio_commit_keeps_eight_numbered_lines(self) -> None:
        """<<studio collect joins with real \\n; commit must not collapse to one line."""
        # Eight logical source lines (empty line is still a logical line).
        author_lines = [
            "# Terminal-Prolog",
            "",
            "The cursor blinks once.",
            "**Boot** sequence.",
            "---",
            "Line six of eight.",
            "Line seven of eight.",
            "Line eight of eight.",
        ]
        body = "\n".join(author_lines)
        self.assertEqual(body.count("\n"), 7)

        meta = {
            "action": "add",
            "book_and_title": "field-notes Terminal-Prolog",
            "studio": True,
        }
        cmd = cli._commit_book_page_multiline(self.world, meta, body)
        # One-line dispatch form: real newlines escaped, not embedded.
        self.assertNotIn("\n", cmd)
        self.assertIn(r"\n", cmd)
        self.assertIn("studio |", cmd)

        r = dispatch(self.world, cmd)
        self.assertTrue(r.ok, msg=r.message)

        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        stored = self.world.list_book_pages(book.id)[0]["body"]
        self.assertTrue(is_studio(stored))
        from dos.studio_text import strip_studio_header

        source = strip_studio_header(stored)
        logical = source.split("\n")
        if logical and logical[-1] == "" and len(logical) > 1:
            logical = logical[:-1]
        self.assertEqual(len(logical), 8, msg=repr(source))
        self.assertIn("Terminal-Prolog", source)
        self.assertIn("Line eight of eight.", source)

        opened = plain(dispatch(self.world, "book open field-notes").message)
        # Eight logical lines stored; blank line 2 unnumbered in the reader
        self.assertRegex(opened, r"(?m)^\s*1\s+")
        self.assertNotRegex(opened, r"(?m)^\s*2\s+")
        for n in range(3, 9):
            self.assertRegex(opened, rf"(?m)^\s*{n}\s+")
        self.assertIn("Terminal-Prolog", opened)
        self.assertIn("Line eight of eight.", opened)
        self.assertNotIn("**Boot**", opened)  # studio markup rendered

        # Edit path: same real-newline body via multiline commit
        body2 = "# Rewritten\nSecond logical line.\nThird."
        meta_edit = {
            "action": "edit",
            "book_name": "field-notes",
            "page": 1,
            "studio": True,
        }
        cmd2 = cli._commit_book_page_multiline(self.world, meta_edit, body2)
        self.assertNotIn("\n", cmd2)
        r2 = dispatch(self.world, cmd2)
        self.assertTrue(r2.ok, msg=r2.message)
        stored2 = strip_studio_header(
            self.world.list_book_pages(book.id)[0]["body"]
        )
        self.assertEqual(len(stored2.split("\n")), 3)
        opened2 = plain(dispatch(self.world, "book open field-notes").message)
        self.assertRegex(opened2, r"(?m)^\s*1\s+")
        self.assertRegex(opened2, r"(?m)^\s*2\s+")
        self.assertRegex(opened2, r"(?m)^\s*3\s+")
        self.assertIn("Rewritten", opened2)

    def test_line_insert_begin_middle_end_via_dispatch(self) -> None:
        dispatch(self.world, "book page add field-notes Core | original")
        r = dispatch(
            self.world,
            "book line insert field-notes 1 1 Opening line.",
        )
        self.assertTrue(r.ok, msg=r.message)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["Opening line.", "original"])

        r = dispatch(
            self.world,
            "book line insert field-notes 1 2 Between them.",
        )
        self.assertTrue(r.ok, msg=r.message)
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(
            split_page_lines(body),
            ["Opening line.", "Between them.", "original"],
        )

        r = dispatch(self.world, "book line add field-notes 1 Closing line.")
        self.assertTrue(r.ok, msg=r.message)
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(
            split_page_lines(body),
            ["Opening line.", "Between them.", "original", "Closing line."],
        )

        r = dispatch(
            self.world,
            "book line insert field-notes 1 5 Very end.",
        )
        self.assertTrue(r.ok, msg=r.message)
        body = self.world.list_book_pages(book.id)[0]["body"]
        lines = split_page_lines(body)
        self.assertEqual(
            lines,
            [
                "Opening line.",
                "Between them.",
                "original",
                "Closing line.",
                "Very end.",
            ],
        )
        opened = plain(dispatch(self.world, "book open field-notes").message)
        for i, text in enumerate(lines, start=1):
            self.assertIn(f"{i}  {text}", opened)

    def test_line_remove_and_move_via_dispatch(self) -> None:
        dispatch(
            self.world,
            r"book page add field-notes P | A\nB\nC\nD",
        )
        r = dispatch(self.world, "book line remove field-notes 1 2")
        self.assertTrue(r.ok, msg=r.message)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["A", "C", "D"])

        r = dispatch(self.world, "book line move field-notes 1 3 1")
        self.assertTrue(r.ok, msg=r.message)
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["D", "A", "C"])

        # multi-page: line ops do not reorder pages
        dispatch(self.world, "book page add field-notes Q | only")
        r = dispatch(self.world, "book line move field-notes 1 1 2")
        self.assertTrue(r.ok, msg=r.message)
        pages = self.world.list_book_pages(book.id)
        self.assertEqual([p["title"] for p in pages], ["P", "Q"])
        self.assertEqual(split_page_lines(pages[0]["body"]), ["A", "D", "C"])
        self.assertEqual(pages[1]["body"], "only")

    def test_line_insert_multi_paragraph_units(self) -> None:
        dispatch(self.world, "book page add field-notes P | tail")
        r = dispatch(
            self.world,
            r"book line insert field-notes 1 1 Para A.\nPara B.",
        )
        self.assertTrue(r.ok, msg=r.message)
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        body = self.world.list_book_pages(book.id)[0]["body"]
        self.assertEqual(split_page_lines(body), ["Para A.", "Para B.", "tail"])

    def test_page_order_unchanged_by_line_amend(self) -> None:
        dispatch(self.world, "book page add field-notes A | a1")
        dispatch(self.world, "book page add field-notes B | b1")
        dispatch(self.world, "book line insert field-notes 1 1 a0")
        dispatch(self.world, "book page insert field-notes 2 Mid | m")
        book = self.world.resolve_here_named("field-notes")
        assert book is not None
        pages = self.world.list_book_pages(book.id)
        self.assertEqual([p["title"] for p in pages], ["A", "Mid", "B"])
        self.assertEqual([p["position"] for p in pages], [1, 2, 3])
        self.assertEqual(split_page_lines(pages[0]["body"]), ["a0", "a1"])


class BookReaderStructureTests(unittest.TestCase):
    def test_book_soft_reader_modal_in_tui(self) -> None:
        src = inspect.getsource(cli.run_textual)
        # Soft full-width modal reader (phase 2) — not a side rail
        self.assertIn("make_book_reader_screen", src)
        self.assertIn("_open_book_reader", src)
        self.assertIn("_close_book_reader", src)
        self.assertIn("IS_BOOK_READER", src)
        self.assertNotIn("book-pane", src)
        self.assertNotIn("_open_book_pane", src)
        self.assertNotIn("action_close_book_pane", src)
        # Buffer editor still available (<<studio and reader e)
        self.assertIn("make_studio_buffer_screen", src)
        self.assertIn("push_screen", src)
        self.assertIn("open_book_id", src)
        # mutual exclusion with help rail
        self.assertIn("_close_help_only", src)

        from dos import book_ui

        br = inspect.getsource(book_ui.make_book_reader_screen)
        self.assertIn("BookReaderScreen", br)
        self.assertIn("action_edit_page", br)
        self.assertIn("action_add_leaf", br)
        self.assertIn("action_prev", br)
        self.assertIn("action_next", br)
        self.assertIn("action_close", br)
        self.assertIn("format_page_body", br)
        self.assertIn("book-reader-header", br)
        self.assertIn("book-reader-scroll", br)
        self.assertIn("book-reader-foot", br)
        self.assertIn("height: 1fr", br)  # body fills frame; scrolls inside
        self.assertIn("height: 80%", br)  # consistent modal height
        self.assertIn("rgba", br)  # soft dim backdrop
        self.assertIn('Binding("e"', br)
        self.assertIn('Binding("plus"', br)  # + add leaf (not bare a)
        self.assertIn("shift+equals", br)  # main-keyboard +
        self.assertIn("_refocus_reader", br)
        self.assertIn("set_book_page_title_by_id", br)  # insert-safe save
        self.assertIn("leaf", br.lower())
        # no side-pane width tokens left on cli
        self.assertFalse(hasattr(cli, "TUI_BOOK_PANE_WIDTH"))


class NestedBookOpenTests(unittest.TestCase):
    """Open/read a book nested in a reachable container without taking it out."""

    def setUp(self) -> None:
        self.world = _world()
        self.assertTrue(
            dispatch(self.world, "create book Nested Codex | Hidden pages.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn nested-codex").ok)
        self.assertTrue(
            dispatch(
                self.world,
                "book page add nested-codex Secret | Nested body line.",
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "create object File Case | Holds papers.").ok
        )
        self.assertTrue(dispatch(self.world, "spawn file-case").ok)

    def _put_book_in_case(self) -> None:
        put = dispatch(self.world, "put nested-codex in case")
        self.assertTrue(put.ok, msg=put.message)

    def test_open_nested_book_on_floor_without_take(self) -> None:
        self._put_book_in_case()
        # Book is not top-level on floor; still openable by unique name
        opened = dispatch(self.world, "book open nested-codex")
        self.assertTrue(opened.ok, msg=opened.message)
        text = plain(opened.message)
        self.assertIn("Nested body line", text)
        self.assertIsNotNone(opened.open_book_id)

        # Still nested after open (no auto-take)
        case = self.world.resolve_here_named("file-case")
        assert case is not None
        inside = self.world.contents(case.id)
        names = [c.name for c in inside]
        self.assertTrue(
            any("codex" in n.lower() or "Nested" in n for n in names),
            msg=f"book left container; inside={names}",
        )
        book = self.world.get_instance(opened.open_book_id)
        assert book is not None
        cont = self.world.container_of(book.id)
        self.assertIsNotNone(cont)
        assert cont is not None
        self.assertEqual(cont[0], case.id)

        # read alias
        r2 = dispatch(self.world, "read nested-codex")
        self.assertTrue(r2.ok, msg=r2.message)
        self.assertIn("Nested body line", plain(r2.message))

    def test_open_nested_book_from_container_qualifier(self) -> None:
        self._put_book_in_case()
        opened = dispatch(self.world, "book open nested-codex from case")
        self.assertTrue(opened.ok, msg=opened.message)
        self.assertIn("Nested body line", plain(opened.message))
        # still nested
        book = self.world.get_instance(opened.open_book_id)
        assert book is not None
        cont = self.world.container_of(book.id)
        assert cont is not None
        case = self.world.resolve_here_named("file-case")
        assert case is not None
        self.assertEqual(cont[0], case.id)

    def test_open_nested_book_in_carried_container(self) -> None:
        self._put_book_in_case()
        take = dispatch(self.world, "take case")
        self.assertTrue(take.ok, msg=take.message)
        opened = dispatch(self.world, "book open nested-codex")
        self.assertTrue(opened.ok, msg=opened.message)
        self.assertIn("Nested body line", plain(opened.message))
        # book still inside carried case, not top-level inv
        book = self.world.get_instance(opened.open_book_id)
        assert book is not None
        cont = self.world.container_of(book.id)
        assert cont is not None
        case = next(
            (c for c in self.world.inventory() if "case" in c.name.lower()),
            None,
        )
        self.assertIsNotNone(case)
        assert case is not None
        self.assertEqual(cont[0], case.id)

    def test_missing_book_still_errors(self) -> None:
        r = dispatch(self.world, "book open no-such-tome-xyz")
        self.assertTrue(r.ok)
        self.assertIn("No", plain(r.message))

    def test_ambiguous_nested_requires_from_or_ref(self) -> None:
        self._put_book_in_case()
        # Second copy of same prime on the floor
        self.assertTrue(dispatch(self.world, "spawn nested-codex").ok)
        amb = dispatch(self.world, "book open nested-codex")
        text = plain(amb.message).lower()
        self.assertIn("ambiguous", text)
        # Explicit from disambiguates the nested one
        opened = dispatch(self.world, "book open nested-codex from case")
        self.assertTrue(opened.ok, msg=opened.message)
        self.assertIn("Nested body line", plain(opened.message))
        # Floor copy still openable by short ref path exists; from empty fails
        bad = dispatch(self.world, "book open nested-codex from pouch")
        self.assertIn("No container", plain(bad.message))


if __name__ == "__main__":
    unittest.main()
