"""Book pages: ordered text outside lore; pure nav + page-view helpers."""

from __future__ import annotations

from typing import Literal

from .measure import CONTENT_MEASURE, wrap_text_hanging

BookStatus = Literal["empty", "incomplete", "complete"]

# Viewer column width for centering title / rules — same artboard as studio
PAGE_VIEW_WIDTH = CONTENT_MEASURE

STATUS_COLORS: dict[str, str] = {
    "empty": "red",
    "incomplete": "yellow",
    "complete": "green",
}


def page_index_after_nav(current: int, delta: int, count: int) -> int:
    """
    Move among pages by delta (-1 prev, +1 next).

    Clamps to [0, count-1]. Empty book stays at 0.
    """
    if count <= 0:
        return 0
    nxt = current + delta
    if nxt < 0:
        return 0
    if nxt >= count:
        return count - 1
    return nxt


def resolve_book_status(*, page_count: int, incomplete: bool) -> BookStatus:
    """
    Book lifecycle label for display.

    - empty: no pages (new books default here)
    - incomplete: has pages and incomplete flag is set
    - complete: has pages and incomplete flag is clear
    """
    if page_count <= 0:
        return "empty"
    if incomplete:
        return "incomplete"
    return "complete"


def format_status_markup(status: str) -> str:
    """Colored status word for Rich/Textual markup (empty red, incomplete yellow, complete green)."""
    color = STATUS_COLORS.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def parse_book_line_ref(token: str) -> tuple[int, int] | None:
    """
    Parse a page:line reference token.

    Accepts ``1:3``, ``p1:3``, ``1.3`` (1-based page and line). Returns
    ``(page, line)`` or None if the token is not a line ref.
    """
    if not token:
        return None
    t = token.strip().lower()
    if t.startswith("p") and len(t) > 1 and t[1].isdigit():
        t = t[1:]
    sep = ":" if ":" in t else ("." if "." in t else None)
    if sep is None:
        return None
    left, _, right = t.partition(sep)
    if not left.isdigit() or not right.isdigit():
        return None
    page, line = int(left), int(right)
    if page < 1 or line < 1:
        return None
    return page, line


def split_page_lines(body: str) -> list[str]:
    """
    Split a page body into ordered logical line units (1-based addresses).

    Empty / whitespace-only body → no lines. Otherwise split on newlines;
    a trailing empty segment from a final newline is dropped.
    """
    if not body:
        return []
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def join_page_lines(lines: list[str]) -> str:
    """Serialize ordered line units back to a page body."""
    if not lines:
        return ""
    return "\n".join(lines)


def _units_from_new_text(new_text: str) -> list[str]:
    """Parse amend payload into one or more line units (must be non-empty)."""
    if new_text is None:
        return []
    text = new_text.replace("\r\n", "\n").replace("\r", "\n")
    if text == "":
        return []
    parts = text.split("\n")
    if parts and parts[-1] == "" and len(parts) > 1:
        parts = parts[:-1]
    if len(parts) == 1 and not parts[0].strip() and parts[0] != "":
        return parts
    if not any(p.strip() for p in parts):
        return []
    return parts


def insert_page_lines(body: str, at: int, new_text: str) -> str:
    """
    Insert one or more line units into a page body at a 1-based position.

    ``at`` is the line number the first new unit becomes (insert before the
    current line ``at``). Valid range: 1 .. len(lines)+1
    (1 = beginning, len+1 = end). Multi-line ``new_text`` adds multiple units.
    After insert, lines renumber contiguously from 1 via join order.
    """
    existing = split_page_lines(body or "")
    incoming = _units_from_new_text(new_text if new_text is not None else "")
    if not incoming:
        raise ValueError("line text must not be empty")
    n = len(existing)
    if at < 1:
        raise ValueError("line position must be >= 1")
    if at > n + 1:
        raise ValueError(f"line position must be between 1 and {n + 1}")
    idx = at - 1
    return join_page_lines(existing[:idx] + incoming + existing[idx:])


def remove_page_line(body: str, line_no: int) -> str:
    """Remove the 1-based line unit; remaining lines renumber contiguously."""
    existing = split_page_lines(body or "")
    n = len(existing)
    if n == 0:
        raise ValueError("page has no lines")
    if line_no < 1 or line_no > n:
        raise ValueError(f"line position must be between 1 and {n}")
    del existing[line_no - 1]
    return join_page_lines(existing)


def move_page_line(body: str, from_line: int, to_line: int) -> str:
    """
    Move a 1-based line unit so it becomes ``to_line`` after the operation.

    Other lines shift to fill the gap. Contiguous renumbering follows join order.
    """
    existing = split_page_lines(body or "")
    n = len(existing)
    if n == 0:
        raise ValueError("page has no lines")
    if from_line < 1 or from_line > n:
        raise ValueError(f"from line must be between 1 and {n}")
    if to_line < 1 or to_line > n:
        raise ValueError(f"to line must be between 1 and {n}")
    if from_line == to_line:
        return join_page_lines(existing)
    item = existing.pop(from_line - 1)
    existing.insert(to_line - 1, item)
    return join_page_lines(existing)


def _escape_plain(text: str) -> str:
    """Escape Rich markup metacharacters in user/world text."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("[", "\\[")
    )


def _line_num_markup(i: int, width: int) -> str:
    """Super-light Bible-style gutter number (logical lines only; soft wrap adds none)."""
    return f"[dim]{i:>{width}}[/dim]"


def _is_blank_logical_line(line: str) -> bool:
    """True when the source line is empty / whitespace-only (no gutter number)."""
    return not (line or "").strip()


def gutter_prefix_width(num_width: int) -> int:
    """Visible columns for ``NN  `` (number gutter + two-space gap)."""
    return max(2, num_width) + 2


def _emit_hanging_rows(
    num_markup: str,
    hang: int,
    segments: list[str],
    *,
    render=None,
) -> list[str]:
    """
    First row: gutter number + gap + first segment.
    Continuations: spaces of length *hang* (clears the gutter) + segment.
    """
    if not segments:
        return [num_markup]
    rows: list[str] = []
    for i, seg in enumerate(segments):
        body = render(seg) if render is not None else seg
        if i == 0:
            rows.append(f"{num_markup}  {body}")
        else:
            rows.append(f"{' ' * hang}{body}")
    return rows


def format_numbered_lines(body: str, *, view_width: int = PAGE_VIEW_WIDTH) -> str:
    """
    Format page body with light Bible-style line numbers on **logical** lines.

    Only newline-separated units get numbers. Blank / whitespace-only lines are
    left unnumbered (still reserve their logical index so non-blank lines keep
    stable addresses for line edit). Long logical lines hard-wrap with a hanging
    indent past the gutter (no extra numbers on wrap).

    Plain bodies: escaped text. Studio bodies (``.format: studio``): Studio Text
    per logical line, still numbered with the same hang-wrap rules.
    """
    from .studio_text import detect_format, is_studio

    if is_studio(body):
        _mode, text = detect_format(body)
        return _format_numbered_studio_lines(text, view_width=view_width)

    lines = split_page_lines(body)
    if not lines:
        return "[dim](empty page)[/dim]"
    num_w = max(2, len(str(len(lines))))
    hang = gutter_prefix_width(num_w)
    content_w = max(8, view_width - hang)
    out: list[str] = []
    for i, line in enumerate(lines, start=1):
        if _is_blank_logical_line(line):
            out.append("")
            continue
        num = _line_num_markup(i, num_w)
        segs = wrap_text_hanging(line, content_w)
        out.extend(
            _emit_hanging_rows(
                num,
                hang,
                segs,
                render=_escape_plain,
            )
        )
    return "\n".join(out)


def _format_numbered_studio_lines(
    source: str, *, view_width: int = PAGE_VIEW_WIDTH
) -> str:
    """Number each source line; render Studio Text features line-by-line with hang wrap."""
    from .studio_text import (
        _FENCE_CLOSE_RE,
        _FENCE_OPEN_RE,
        _HEADING_RE,
        _RULE_RE,
        _field_row_match,
        _label_col_width,
        _render_heading,
        _render_inline,
        format_fence_box_parts,
        safe,
    )

    text = (source or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "" and len(lines) > 1:
        lines = lines[:-1]
    if not lines or (len(lines) == 1 and not lines[0].strip()):
        return "[dim](empty page)[/dim]"

    # Contiguous field blocks share one key column width (aligned values)
    field_col: dict[int, int] = {}
    fi = 0
    while fi < len(lines):
        if _field_row_match(lines[fi]) is None:
            fi += 1
            continue
        labs: list[str] = []
        fj = fi
        while fj < len(lines):
            fr = _field_row_match(lines[fj])
            if fr is None:
                break
            labs.append(fr[0])
            fj += 1
        col_w = _label_col_width(labs)
        for k in range(fi, fj):
            field_col[k] = col_w
        fi = fj

    num_w = max(2, len(str(len(lines))))
    hang = gutter_prefix_width(num_w)
    content_w = max(8, view_width - hang)
    out: list[str] = []
    in_fence = False
    fence_kind = "seed"
    fence_buf: list[str] = []
    fence_open_i = 0
    for i, line in enumerate(lines, start=1):
        num = _line_num_markup(i, num_w)
        if in_fence:
            if _FENCE_CLOSE_RE.match(line):
                in_fence = False
                top, pad_b, content_rows, pad_a, bot = format_fence_box_parts(
                    fence_buf,
                    fence_kind,
                    max_inner=max(4, content_w - 2),
                )
                # Line rail: open → top, each source body line → content row,
                # pad rows unnumbered, close → bottom. (Padding must not steal
                # body numbers — that caused jumps of 2 after the box.)
                out.append(f"{_line_num_markup(fence_open_i, num_w)}  {top}")
                for row in pad_b:
                    out.append(f"{' ' * hang}{row}")
                if fence_buf:
                    for j, row in enumerate(content_rows):
                        src_i = fence_open_i + 1 + j
                        out.append(
                            f"{_line_num_markup(src_i, num_w)}  {row}"
                        )
                else:
                    # Hollow interior — no source line
                    for row in content_rows:
                        out.append(f"{' ' * hang}{row}")
                for row in pad_a:
                    out.append(f"{' ' * hang}{row}")
                out.append(f"{num}  {bot}")
                fence_buf = []
            else:
                fence_buf.append(line)
            continue
        fm = _FENCE_OPEN_RE.match(line)
        if fm:
            in_fence = True
            fence_kind = (fm.group(1) or "").strip() or "seed"
            fence_buf = []
            fence_open_i = i
            continue
        if _RULE_RE.match(line) and line.strip():
            # Full content measure (72), not the short decorative 36
            out.append(f"{num}  [dim]{'─' * PAGE_VIEW_WIDTH}[/dim]")
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            # Wrap heading source text, re-apply heading style on first seg only
            level = len(hm.group(1))
            title = hm.group(2).strip()
            segs = wrap_text_hanging(title, content_w)
            for j, seg in enumerate(segs):
                if j == 0:
                    out.append(f"{num}  {_render_heading(level, seg)}")
                else:
                    out.append(f"{' ' * hang}{_render_heading(level, seg)}")
            continue
        if line.startswith("> "):
            segs = wrap_text_hanging(line[2:], max(1, content_w - 2))
            for j, seg in enumerate(segs):
                piece = f"[dim]│ {_render_inline(seg)}[/dim]"
                if j == 0:
                    out.append(f"{num}  {piece}")
                else:
                    out.append(f"{' ' * hang}{piece}")
            continue
        fr = _field_row_match(line)
        if fr is not None:
            lab, val = fr
            col_w = field_col.get(i - 1, _label_col_width([lab]))
            lab_s = safe(lab).ljust(col_w)
            # First segment carries the label; wrap value under value column
            prefix_plain = f"{lab.ljust(col_w)}  "
            value_hang = hang + len(prefix_plain)
            segs = wrap_text_hanging(val, max(8, content_w - len(prefix_plain)))
            for j, seg in enumerate(segs):
                if j == 0:
                    out.append(
                        f"{num}  [dim]{lab_s}[/dim]  {_render_inline(seg)}"
                    )
                else:
                    out.append(f"{' ' * value_hang}{_render_inline(seg)}")
            continue
        if _is_blank_logical_line(line):
            # Pure breathing room — no gutter digit (index still reserved)
            out.append("")
            continue
        segs = wrap_text_hanging(line, content_w)
        out.extend(
            _emit_hanging_rows(num, hang, segs, render=_render_inline)
        )
    return "\n".join(out)


def _center(text: str, width: int) -> str:
    t = text if len(text) <= width else text[:width]
    pad = max(0, (width - len(t)) // 2)
    return (" " * pad) + t


def format_page_body(
    *,
    page_index: int,
    page_count: int,
    title: str,
    body: str,
    width: int = PAGE_VIEW_WIDTH,
) -> str:
    """
    Inner page content only (no book chrome) — for the TUI reader scroll area.

    Centered ALL-CAPS page title + numbered body at *width* measure.
    """
    n = page_index + 1 if page_count else 0
    if page_count <= 0:
        return "[dim](empty book — press + to add a leaf)[/dim]"
    raw_title = (title or "").strip() or f"Page {n}"
    page_title = _center(raw_title.upper(), width)
    numbered = format_numbered_lines(body, view_width=width)
    return "\n".join([page_title, "", numbered])


def format_page_view(
    *,
    book_name: str,
    status: str,
    page_index: int,
    page_count: int,
    title: str,
    body: str,
    width: int = PAGE_VIEW_WIDTH,
) -> str:
    """
    Full page view for REPL: chrome bar, title, numbered body, page footer.
    Status is colorized. TUI reader uses chrome widgets + :func:`format_page_body`.
    """
    status_mk = format_status_markup(status)
    name = _escape_plain(book_name)
    chrome = f"{name}  ·  {status_mk}"
    # ASCII rule so pages match the content measure and export cleanly
    rule = "-" * width
    n = page_index + 1 if page_count else 0
    footer = f"page {n}/{page_count}"
    inner = format_page_body(
        page_index=page_index,
        page_count=page_count,
        title=title,
        body=body,
        width=width,
    )

    if page_count <= 0:
        return "\n".join(
            [
                chrome,
                "",
                rule,
                "",
                inner,
                "",
                rule,
                footer,
            ]
        )

    return "\n".join(
        [
            chrome,
            "",
            rule,
            "",
            inner,
            "",
            rule,
            footer,
        ]
    )
