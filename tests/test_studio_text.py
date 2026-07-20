"""Studio Text renderer + opt-in @desc / lore integration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from wbs_seed_fixtures import seed_world_story
from dos.studio_text import (
    FORMAT_HEADER,
    detect_format,
    is_openable_url,
    prepare_stored_text,
    render_body,
    render_open_link,
    render_studio_text,
    with_studio_header,
)
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_story(conn)
    return World(conn)


class StudioTextUnitTests(unittest.TestCase):
    def test_plain_escapes_brackets(self) -> None:
        raw = "Hello [bold red]hack[/bold red] **still plain**"
        out = render_body(raw)
        self.assertIn("\\[", out)
        # must not be live Rich open tag (escaped bracket)
        self.assertNotIn("[bold red]hack", out.replace("\\[", ""))
        # literal stars remain visible as text after plain()
        self.assertIn("**still plain**", plain(out))

    def test_studio_header_and_emphasis(self) -> None:
        body = with_studio_header("# Title\n\n**Bold** and _soft_ and `code`")
        mode, _ = detect_format(body)
        self.assertEqual(mode, "studio")
        self.assertTrue(body.startswith(FORMAT_HEADER))
        rendered = render_body(body)
        self.assertIn("[bold", rendered)
        self.assertIn("yellow", rendered)  # # heading
        p = plain(rendered)
        self.assertIn("Title", p)
        self.assertIn("Bold", p)
        self.assertIn("soft", p)
        self.assertIn("code", p)
        # attacker tags in free text still escaped (\\[ not live tag)
        evil = with_studio_header("x [bold red]nope[/bold red] y")
        er = render_body(evil)
        self.assertIn("\\[bold red]", er)
        self.assertNotIn("[bold red]nope", er.replace("\\[", "X"))

    def test_color_spans_whitelist(self) -> None:
        from dos.studio_text import render_studio_text, STUDIO_COLORS

        out = render_studio_text("{yellow}gold path{/} and {r}danger{/r}")
        self.assertIn("[yellow]", out)
        self.assertIn("[red]", out)
        p = plain(out)
        self.assertIn("gold path", p)
        self.assertIn("danger", p)
        # nested emphasis inside color
        out2 = render_studio_text("{cyan}**bold cyan**{/}")
        self.assertIn("[cyan]", out2)
        self.assertIn("[bold]", out2)
        # unknown color not injected as Rich
        evil = render_studio_text("{notacolor}x{/}")
        self.assertNotIn("[notacolor]", evil)
        self.assertIn("x", plain(evil))
        # raw Rich in free text still escaped
        evil2 = render_studio_text("x [bold red]nope[/bold red] y")
        self.assertIn("\\[bold red]", evil2)
        self.assertIn("yellow", STUDIO_COLORS)
        self.assertIn("accent", STUDIO_COLORS)

    def test_rules_fence_wiki_label_frontmatter(self) -> None:
        src = """---
title: Space Travel
when: Pending
type: prophecy
---
# Banner

---

:CRATE-ID: WWW-1
**ORIGIN:** home

[[093.002 Chat]]

```seed
.....dots.....
literal line
```

@end #space
"""
        out = render_studio_text(src)
        p = plain(out)
        self.assertIn("Space Travel", p)
        self.assertIn("Pending", p)
        self.assertIn("prophecy", p)
        self.assertIn("Banner", p)
        self.assertIn("CRATE-ID", p)
        self.assertIn("WWW-1", p)
        self.assertIn("093.002 Chat", p)
        self.assertIn("dots", p)
        self.assertIn("literal line", p)
        self.assertIn("seed", p)  # fence label in top rail
        self.assertIn("─", out)  # box + page rules use box-drawing
        self.assertIn("[cyan]", out)  # wikilink color
        self.assertIn("┌", p)  # light content-sized box
        self.assertIn("└", p)
        self.assertIn("│", p)

    def test_external_links_md_and_bare(self) -> None:
        """Markdown and bare https links become clickable open_url markup."""
        out = render_studio_text(
            "See [docs](https://example.com/path) and https://x.ai/ for more."
        )
        self.assertIn("@click=app.open_url('https://example.com/path')", out)
        self.assertIn("@click=app.open_url('https://x.ai/')", out)
        self.assertIn("underline", out)
        p = plain(out)
        self.assertIn("docs", p)
        self.assertIn("https://x.ai/", p)
        # trailing prose punctuation not swallowed into the URL
        out2 = render_studio_text("go https://example.com.")
        self.assertIn("@click=app.open_url('https://example.com')", out2)
        self.assertTrue(out2.rstrip().endswith(".") or plain(out2).endswith("."))
        # code fence keeps URLs literal (no click action)
        out3 = render_studio_text("use `https://example.com` as text")
        self.assertNotIn("@click=", out3)
        self.assertIn("https://example.com", plain(out3))
        # unsafe / non-http stays plain
        self.assertFalse(is_openable_url("javascript:alert(1)"))
        self.assertFalse(is_openable_url("file:///etc/passwd"))
        self.assertTrue(is_openable_url("https://example.com"))
        plain_bad = render_open_link("javascript:alert(1)", "nope")
        self.assertNotIn("@click=", plain_bad)
        self.assertIn("nope", plain(plain_bad))

    def test_field_row_value_hangs_under_value_column(self) -> None:
        """Long field values wrap with hang indent, not column 0."""
        long = "word " * 40  # well past measure 72
        src = f":Notes: {long.strip()}\n:Ok: yes\n"
        p = plain(render_studio_text(src))
        lines = [ln for ln in p.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 2)
        # First line has label; later lines are pure value with leading spaces
        notes_lines = [ln for ln in lines if "word" in ln or ln.lstrip().startswith("word")]
        # At least one continuation (hang) after the first Notes line
        self.assertGreaterEqual(len(notes_lines), 2)
        first = notes_lines[0]
        cont = notes_lines[1]
        self.assertIn("Notes", first)
        self.assertNotIn("Notes", cont)
        # Continuation starts at value column (spaces), not left edge of content
        self.assertTrue(cont.startswith(" "), msg=repr(cont[:20]))
        # Value column: padded "Notes" (min 8) + two spaces
        hang = first.index("word")
        self.assertEqual(cont.index("word"), hang, msg=f"first={first!r}\ncont={cont!r}")

    def test_field_rows_align_value_column(self) -> None:
        """Contiguous :Key: value (and bare Key: value) share one pad width."""
        src = """\
:Design start: 2024-01-03
:QA: 2024-06-01
:Release: 2024-07-15
Art: 2024-03-01
"""
        p = plain(render_studio_text(src))
        lines = [ln for ln in p.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 3)
        # Value column starts at the same index for the :Key: block
        # (after padded key + two spaces)
        def val_col(line: str, key: str) -> int:
            i = line.index(key)
            # skip key and following spaces to first non-space of value
            j = i + len(key)
            while j < len(line) and line[j] == " ":
                j += 1
            return j

        c0 = val_col(lines[0], "Design start")
        c1 = val_col(lines[1], "QA")
        c2 = val_col(lines[2], "Release")
        self.assertEqual(c0, c1)
        self.assertEqual(c1, c2)
        self.assertIn("2024-01-03", lines[0])
        self.assertIn("Art", lines[3])

    def test_unnamed_fence_seed_box(self) -> None:
        out = render_studio_text("before\n```\ncode here\n```\nafter")
        p = plain(out)
        self.assertIn("seed", p)
        self.assertIn("code here", p)
        self.assertIn("┌", p)
        self.assertIn("└", p)
        # box sized to content, not a full-width page rule bar alone
        self.assertTrue(any(line.strip().startswith("┌") for line in p.splitlines()))
        # minor inner padding: space after left bar before content
        self.assertIn("│ code here", p)

    def test_fence_inner_padding(self) -> None:
        from dos.studio_text import format_fence_box
        from dos.format import plain as pl

        rows = format_fence_box(["X"], "seed")
        text = pl("\n".join(rows))
        lines = text.splitlines()
        # top, pad row, content, pad row, bottom
        self.assertGreaterEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("┌"))
        self.assertTrue(lines[-1].startswith("└"))
        # blank padded row (only spaces between bars)
        self.assertRegex(lines[1], r"^│\s+│$")
        self.assertIn("│ X ", lines[2])

    def test_named_fence_label_in_top_rail(self) -> None:
        out = render_studio_text("```map\nA→B\n```")
        p = plain(out)
        self.assertIn("map", p)
        self.assertIn("A→B", p)
        self.assertIn("┌", p)

    def test_prepare_stored(self) -> None:
        s = prepare_stored_text("**Hi**", studio=True)
        self.assertTrue(s.startswith(FORMAT_HEADER))
        self.assertIn("**Hi**", s)


class StudioTextDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _world()

    def test_desc_studio_look_and_plain_default(self) -> None:
        # plain default still literal stars
        dispatch(self.world, "@desc Just **stars** plain.")
        look_plain = plain(dispatch(self.world, "look").message)
        self.assertIn("**stars**", look_plain)

        r = dispatch(
            self.world,
            r"@desc studio | # Hearth Note\n\n**Resonance** travel — not rockets.\n---\n[[Story Road]]",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("studio", plain(r.message).lower())
        loc = self.world.player_location()
        assert loc is not None
        ov = self.world.get_description_override(loc.id)
        assert ov is not None
        self.assertTrue(ov.startswith(FORMAT_HEADER))

        look = dispatch(self.world, "look")
        raw = look.message
        text = plain(raw)
        self.assertIn("Hearth Note", text)
        self.assertIn("Resonance", text)
        self.assertIn("Story Road", text)
        # markup present in Rich path
        self.assertIn("[bold", raw)
        # no mid-dot turn sep regression; description not fully escaped stars
        self.assertNotIn("**Resonance**", text)

        shown = plain(dispatch(self.world, "@desc").message)
        self.assertIn("Hearth Note", shown)

    def test_lore_studio_list_and_examine_signal(self) -> None:
        r = dispatch(
            self.world,
            "lore add studio | Prophecy | **SPACE TRAVEL.**\\n---\\nNot NASA.",
        )
        self.assertTrue(r.ok, msg=r.message)
        listed = dispatch(self.world, "lore")
        text = plain(listed.message)
        self.assertIn("Prophecy", text)
        self.assertIn("SPACE TRAVEL", text)
        self.assertIn("Not NASA", text)
        # body rendered, not raw stars
        self.assertNotIn("**SPACE TRAVEL.**", text)
        self.assertIn("[bold", listed.message)

    def test_desc_on_instance_studio(self) -> None:
        dispatch(self.world, "create object Relic | plain ven text")
        dispatch(self.world, "spawn relic as Relic One")
        r = dispatch(
            self.world,
            "@desc on relic one studio | # Relic\\n\\n_whispering_ metal",
        )
        self.assertTrue(r.ok, msg=r.message)
        ex = dispatch(self.world, "examine relic one")
        text = plain(ex.message)
        self.assertIn("Relic", text)
        self.assertIn("whispering", text)
        self.assertIn("[italic", ex.message)


if __name__ == "__main__":
    unittest.main()
