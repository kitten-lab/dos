"""Studio Text: opt-in whitelist markup for desc / lore (and later books).

Default world text stays plain (fully escaped). Bodies that opt into studio
mode are stored with a leading magic header and rendered to safe Rich markup.
"""

from __future__ import annotations

import re
from typing import Literal

from .format import safe

TextFormat = Literal["plain", "studio"]

FORMAT_HEADER = ".format: studio"
_FORMAT_HEADER_RE = re.compile(
    r"^\s*\.format\s*:\s*(studio|plain)\s*\n?",
    re.IGNORECASE,
)

# Decorative full-line rules (CRATE-style dots / dashes / equals)
_RULE_RE = re.compile(r"^[\s\-_=─.]{3,}\s*$")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")
_FENCE_OPEN_RE = re.compile(r"^```(\w*)\s*$")
_FENCE_CLOSE_RE = re.compile(r"^```\s*$")
# Field row: :Label: value  (colons wrap the key — stable for multi-word labels)
_LABEL_ROW_RE = re.compile(r"^:([^:]+):\s*(.*)$")
# Also: bare Key: value (single-token key, for quick roadmap fields)
_BARE_FIELD_RE = re.compile(r"^([A-Za-z][\w./-]{0,31}):\s+(.+)$")
_FRONTMATTER_END = re.compile(r"^---\s*$")

# Column pad for field keys (dynamic per contiguous block, clamped)
_LABEL_COL_MIN = 8
_LABEL_COL_MAX = 28

# Inline emphasis (non-greedy, no newlines)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")
_ITALIC_RE = re.compile(r"(?<!\w)_([^_\n]+)_(?!\w)")
_WIKI_RE = re.compile(r"\[\[([^\]]+)\]\]")
# External links: [label](https://…)  or bare https?://…
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"(?<![\w/@])(https?://[^\s\[\]<>\"']+)")
_AT_TAG_RE = re.compile(r"(?<!\w)@([\w][\w-]*)")
_HASH_TAG_RE = re.compile(r"(?<!\w)#([\w][\w-]*)")
# Author color: {yellow}text{/} or {yellow}text{/yellow}  (whitelist only)
_COLOR_SPAN_RE = re.compile(
    r"\{([a-zA-Z][\w-]*)\}([^\n{]+?)\{/(?:\1)?\}"
)

# Trailing punctuation often glued to bare URLs in prose
_URL_TRAIL_CHARS = ".,;:!?)]}\"'>"

# Whitelist name → Rich color/style token (no free-form injection)
STUDIO_COLORS: dict[str, str] = {
    # full names
    "yellow": "yellow",
    "red": "red",
    "green": "green",
    "cyan": "cyan",
    "blue": "blue",
    "magenta": "magenta",
    "white": "white",
    "black": "bright_black",
    # short aliases
    "y": "yellow",
    "r": "red",
    "g": "green",
    "c": "cyan",
    "b": "blue",
    "m": "magenta",
    "w": "white",
    # product / semantic
    "gold": "#d4a574",  # STUDIO Writer brand warmth
    "accent": "bright_cyan",
    "a": "bright_cyan",
    "ok": "green",
    "warn": "yellow",
    "err": "red",
    "dim": "dim",
    "bright": "bright_white",
}


def detect_format(text: str | None) -> tuple[TextFormat, str]:
    """
    Return (mode, body_without_header).

    Studio mode if body starts with ``.format: studio`` (case-insensitive).
    """
    if not text:
        return "plain", ""
    m = _FORMAT_HEADER_RE.match(text)
    if not m:
        return "plain", text
    mode = m.group(1).lower()
    body = text[m.end() :]
    if mode == "studio":
        return "studio", body
    return "plain", body


def with_studio_header(body: str) -> str:
    """Prefix body for storage so display uses studio rendering."""
    body = body if body is not None else ""
    mode, rest = detect_format(body)
    if mode == "studio":
        return f"{FORMAT_HEADER}\n{rest.lstrip('\n')}"
    return f"{FORMAT_HEADER}\n{body.lstrip('\n')}"


def strip_studio_header(text: str | None) -> str:
    """Body without format header (for editing/display of source)."""
    _mode, body = detect_format(text or "")
    return body


def is_studio(text: str | None) -> bool:
    return detect_format(text or "")[0] == "studio"


def render_body(text: str | None) -> str:
    """
    Render stored world text: studio dialect or plain escape.

    Empty → dim placeholder (matches ``format.prose``).
    """
    if text is None or not str(text).strip():
        return "[dim](no description)[/dim]"
    mode, body = detect_format(text)
    if mode == "studio":
        if not body.strip():
            return "[dim](no description)[/dim]"
        return render_studio_text(body)
    # plain — escape entire string; preserve newlines for multi-line descs
    return safe(text)


def _field_row_match(line: str) -> tuple[str, str] | None:
    """Return (label, value) for a field row, or None."""
    m = _LABEL_ROW_RE.match(line)
    if m:
        return m.group(1).strip(), m.group(2)
    m2 = _BARE_FIELD_RE.match(line)
    if m2:
        return m2.group(1).strip(), m2.group(2)
    return None


def _label_col_width(labels: list[str]) -> int:
    """Pad width so value column lines up; clamp for ~72 measure."""
    if not labels:
        return _LABEL_COL_MIN
    w = max(len(lab) for lab in labels)
    return max(_LABEL_COL_MIN, min(_LABEL_COL_MAX, w))


def _render_field_row(lab: str, val: str, col_w: int) -> str:
    """
    One field row: label column + value, hard-wrapped under the value column.

    Continuations hang at ``col_w + 2`` spaces (padded key + gap) so soft wrap
    does not slam long values back to column 0.
    """
    from .measure import CONTENT_MEASURE, wrap_text_hanging

    lab_s = safe(lab).ljust(col_w)
    hang = col_w + 2  # plain-width prefix before value
    # Value width inside the artboard (label + gap already spent)
    val_w = max(8, CONTENT_MEASURE - hang)
    segs = wrap_text_hanging(val if val is not None else "", val_w)
    rows: list[str] = []
    for j, seg in enumerate(segs):
        body = _render_inline(seg)
        if j == 0:
            rows.append(f"[dim]{lab_s}[/dim]  {body}")
        else:
            rows.append(f"{' ' * hang}{body}")
    return "\n".join(rows)


def render_studio_text(source: str) -> str:
    """Parse Studio Text → Rich markup (whitelist only)."""
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    meta, body = _split_frontmatter(text)
    out: list[str] = []
    if meta:
        out.extend(_render_frontmatter(meta))
        out.append("")

    lines = body.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # fenced block
        fm = _FENCE_OPEN_RE.match(line)
        if fm:
            fence_lines: list[str] = []
            i += 1
            while i < n and not _FENCE_CLOSE_RE.match(lines[i]):
                fence_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # consume closing fence
            out.append(_render_fence(fence_lines, fm.group(1) or "seed"))
            continue

        if _RULE_RE.match(line) and line.strip():
            from .measure import CONTENT_MEASURE

            out.append(f"[dim]{'─' * CONTENT_MEASURE}[/dim]")
            i += 1
            continue

        hm = _HEADING_RE.match(line)
        if hm:
            level, title = len(hm.group(1)), hm.group(2).strip()
            out.append(_render_heading(level, title))
            i += 1
            continue

        if line.startswith("> "):
            quote = line[2:]
            out.append(f"[dim]│ {_render_inline(quote)}[/dim]")
            i += 1
            continue

        # Contiguous field block — pad keys to one column for the block
        fr = _field_row_match(line)
        if fr is not None:
            block: list[tuple[str, str]] = []
            while i < n:
                fr_i = _field_row_match(lines[i])
                if fr_i is None:
                    break
                block.append(fr_i)
                i += 1
            col_w = _label_col_width([lab for lab, _ in block])
            for lab, val in block:
                out.append(_render_field_row(lab, val, col_w))
            continue

        if not line.strip():
            out.append("")
            i += 1
            continue

        out.append(_render_inline(line))
        i += 1

    # Trim trailing blank lines
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) if out else "[dim](empty)[/dim]"


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Optional YAML-like frontmatter between leading --- fences."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    i = 1
    while i < len(lines):
        if lines[i].strip() == "---":
            body = "\n".join(lines[i + 1 :])
            return meta, body
        line = lines[i]
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip().strip('"').strip("'")
        i += 1
    return {}, text


def _render_frontmatter(meta: dict[str, str]) -> list[str]:
    from .measure import CONTENT_MEASURE

    rule = f"[dim]{'─' * CONTENT_MEASURE}[/dim]"
    lines = [rule]
    order = ("title", "type", "when", "status", "origin", "handler")
    rows: list[tuple[str, str, bool]] = []  # key, val, bold_val
    seen: set[str] = set()
    for key in order:
        if key in meta and meta[key]:
            seen.add(key)
            rows.append((key, meta[key], True))
    for key, val in meta.items():
        if key in seen or not val:
            continue
        rows.append((key, val, False))
    col_w = _label_col_width([k for k, _, _ in rows])
    for key, val, bold in rows:
        lab = safe(key).ljust(col_w)
        if bold:
            lines.append(f"[dim]{lab}[/dim]  [bold]{safe(val)}[/bold]")
        else:
            lines.append(f"[dim]{lab}[/dim]  {safe(val)}")
    lines.append(rule)
    return lines


def _render_heading(level: int, title: str) -> str:
    """
    # yellow bold (book leaf titles that read as section heads)
    ## bold
    ### dim
    """
    inner = _render_inline(title)
    if level == 1:
        # Yellow — distinct from cyan UI chrome / ACCENT so # reads as content
        return f"[bold yellow]{inner}[/bold yellow]"
    if level == 2:
        return f"[bold]{inner}[/bold]"
    return f"[dim]{inner}[/dim]"


# Spaces between vertical bars and content; blank rows under top / above bottom.
FENCE_PAD_X = 1
FENCE_PAD_Y = 1


def fence_label(kind: str | None) -> str:
    """Display name for a fence; unnamed opens default to ``seed``."""
    return (kind or "").strip() or "seed"


def format_fence_box_parts(
    lines: list[str],
    kind: str | None = None,
    *,
    max_inner: int | None = None,
) -> tuple[str, list[str], list[str], list[str], str]:
    """
    Light box parts for a fenced segment.

    Returns ``(top, pad_before, content_rows, pad_after, bottom)`` as Rich
    markup strings. Book line rails number only *content_rows* (plus top/bottom
    mapped to the open/close fence source lines); pad rows stay unnumbered.
    """
    label = fence_label(kind)
    body = list(lines) if lines is not None else []
    px = max(0, int(FENCE_PAD_X))
    py = max(0, int(FENCE_PAD_Y))

    # Content column width (before side padding)
    content_w = max((len(ln) for ln in body), default=0)
    # Full inner width between vertical bars = pad + content + pad
    min_for_label = len(label) + 4  # "─ " + label + " " + "─"
    inner = max(content_w + 2 * px, min_for_label, 4 + 2 * px)
    if max_inner is not None and max_inner >= 4:
        if inner > max_inner:
            inner = max_inner
    usable = max(0, inner - 2 * px)

    prefix = f"─ {label} "
    if len(prefix) >= inner:
        top_inner = prefix[:inner]
    else:
        top_inner = prefix + ("─" * (inner - len(prefix)))
    top = f"[dim]┌{top_inner}┐[/dim]"
    bot = f"[dim]└{'─' * inner}┘[/dim]"

    def _blank_row() -> str:
        return f"[dim]│{' ' * inner}│[/dim]"

    def _content_row(ln: str) -> str:
        raw = ln if len(ln) <= usable else ln[:usable]
        mid = (" " * px) + safe(raw) + (" " * (usable - len(raw))) + (" " * px)
        return f"[dim]│[/dim]{mid}[dim]│[/dim]"

    pad_before = [_blank_row() for _ in range(py)]
    if body:
        content_rows = [_content_row(ln) for ln in body]
    else:
        # Hollow: one empty interior row (not a source line)
        content_rows = [_blank_row()]
    pad_after = [_blank_row() for _ in range(py)]
    return top, pad_before, content_rows, pad_after, bot


def format_fence_box(
    lines: list[str],
    kind: str | None = None,
    *,
    max_inner: int | None = None,
) -> list[str]:
    """
    Light box around a fenced segment — best practice for ASCII art / diagrams.

    Shape (dim border, normal-weight interior, minor inner padding)::

        ┌─ seed ──────────┐
        │                 │
        │  diagram here   │
        │                 │
        └─────────────────┘

    * Sized to the content (not full page width) so small diagrams don’t
      float in a huge empty frame.
    * Unnamed fences label as ``seed``; `` ```map `` uses that name in the top rail.
    * Distinct from page ``---`` rules (those are plain ─ runs without corners).
    """
    top, pad_b, content, pad_a, bot = format_fence_box_parts(
        lines, kind, max_inner=max_inner
    )
    return [top, *pad_b, *content, *pad_a, bot]


def _render_fence(lines: list[str], kind: str) -> str:
    """Rich markup for a fenced block (light content-sized box)."""
    return "\n".join(format_fence_box(lines, kind))


def resolve_studio_color(name: str) -> str | None:
    """Map author color name to a Rich token, or None if not on the whitelist."""
    return STUDIO_COLORS.get((name or "").strip().lower())


def is_openable_url(url: str) -> bool:
    """True if *url* is a safe http(s) target for browser open from the TUI."""
    u = (url or "").strip()
    if not u or len(u) > 2000:
        return False
    if any(c in u for c in "\n\r\t []"):
        return False
    low = u.lower()
    if not (low.startswith("https://") or low.startswith("http://")):
        return False
    host = u.split("://", 1)[1].split("/")[0].split("?")[0].split("#")[0]
    host = host.split("@")[-1]  # drop userinfo if present
    if not host or host.startswith("."):
        return False
    return True


def _action_quote(url: str) -> str:
    """Quote *url* as a Python string literal for Textual ``@click`` actions."""
    if "'" not in url:
        return f"'{url}'"
    if '"' not in url:
        return f'"{url}"'
    return "'" + url.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _split_bare_url(raw: str) -> tuple[str, str]:
    """Return (url, trailing_punct) for a bare-URL match."""
    url = raw
    trail = ""
    while url and url[-1] in _URL_TRAIL_CHARS:
        trail = url[-1] + trail
        url = url[:-1]
    return url, trail


def render_open_link(url: str, label: str | None = None) -> str:
    """
    Rich/Textual markup for a clickable external link.

    Emits cyan+underline text with ``@click=app.open_url(...)`` so a left-click
    (or terminal hyperlink handling where supported) opens the system browser.
    Unknown/unsafe URLs fall back to escaped plain text.
    """
    u = (url or "").strip()
    text = label if label is not None else u
    if not is_openable_url(u):
        return safe(text)
    q = _action_quote(u)
    return (
        f"[cyan underline][@click=app.open_url({q})]{safe(text)}[/][/]"
    )


def _render_inline(text: str, *, _depth: int = 0) -> str:
    """
    Apply inline Studio Text transforms, escaping free text segments.

    Order: extract protected spans (code, color, wiki, md-link, bare-url,
    bold, italic, tags) via iterative replace with placeholders, then escape
    remainder, then restore.

    Color spans: ``{yellow}text{/}`` or ``{yellow}text{/yellow}`` — whitelist
    only (see :data:`STUDIO_COLORS`). Nested markup inside a span is allowed.
    External links: ``[label](https://…)`` or bare ``https://…`` — click opens
    the system browser (see :func:`render_open_link`).
    """
    if not text:
        return ""

    slots: list[str] = []

    def stash(markup: str) -> str:
        slots.append(markup)
        return f"\x00{len(slots) - 1}\x00"

    s = text

    def repl_code(m: re.Match[str]) -> str:
        return stash(f"[bold]{safe(m.group(1))}[/bold]")

    def repl_color(m: re.Match[str]) -> str:
        token = resolve_studio_color(m.group(1))
        if not token:
            # Unknown name — leave raw for escape (no injection)
            return m.group(0)
        inner_src = m.group(2)
        if _depth < 4:
            inner = _render_inline(inner_src, _depth=_depth + 1)
        else:
            inner = safe(inner_src)
        if token == "dim":
            return stash(f"[dim]{inner}[/dim]")
        return stash(f"[{token}]{inner}[/{token}]")

    def repl_wiki(m: re.Match[str]) -> str:
        return stash(f"[cyan]⟦{safe(m.group(1))}⟧[/cyan]")

    def repl_md_link(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        if not is_openable_url(url):
            return m.group(0)
        return stash(render_open_link(url, label))

    def repl_bare_url(m: re.Match[str]) -> str:
        raw = m.group(1)
        url, trail = _split_bare_url(raw)
        if not is_openable_url(url):
            return m.group(0)
        return stash(render_open_link(url, url)) + trail

    def repl_bold(m: re.Match[str]) -> str:
        return stash(f"[bold]{safe(m.group(1))}[/bold]")

    def repl_italic(m: re.Match[str]) -> str:
        return stash(f"[italic dim]{safe(m.group(1))}[/italic dim]")

    def repl_at(m: re.Match[str]) -> str:
        return stash(f"[dim]@{safe(m.group(1))}[/dim]")

    def repl_hash(m: re.Match[str]) -> str:
        return stash(f"[dim]#{safe(m.group(1))}[/dim]")

    # code first so `{yellow}` inside `…` stays literal
    s = _CODE_RE.sub(repl_code, s)
    s = _COLOR_SPAN_RE.sub(repl_color, s)
    s = _WIKI_RE.sub(repl_wiki, s)
    s = _MD_LINK_RE.sub(repl_md_link, s)
    s = _BARE_URL_RE.sub(repl_bare_url, s)
    s = _BOLD_RE.sub(repl_bold, s)
    s = _ITALIC_RE.sub(repl_italic, s)
    s = _AT_TAG_RE.sub(repl_at, s)
    s = _HASH_TAG_RE.sub(repl_hash, s)

    # Escape free segments between placeholders
    parts = re.split(r"(\x00\d+\x00)", s)
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        m = re.fullmatch(r"\x00(\d+)\x00", part)
        if m:
            out.append(slots[int(m.group(1))])
        else:
            out.append(safe(part))
    return "".join(out)


def peel_studio_prefix(raw: str) -> tuple[bool, str]:
    """
    Peel author opt-in prefixes from a command payload.

    Recognizes:
      studio | <body>
      studio <body>     (if body does not look like a lone word command)
      format studio | <body>

    Returns (want_studio, remainder).
    """
    s = (raw or "").strip()
    if not s:
        return False, ""
    low = s.lower()
    if low.startswith("format studio"):
        rest = s[len("format studio") :].strip()
        if rest.startswith("|"):
            rest = rest[1:].strip()
        return True, rest
    if low.startswith("studio"):
        rest = s[6:].strip()
        if rest.startswith("|"):
            rest = rest[1:].strip()
        return True, rest
    return False, s


def prepare_stored_text(raw: str, *, studio: bool) -> str:
    """Normalize text for DB: add studio header when requested."""
    text = raw if raw is not None else ""
    if studio:
        return with_studio_header(text)
    # if author already included header, keep it
    mode, _ = detect_format(text)
    if mode == "studio":
        return with_studio_header(strip_studio_header(text))
    return text
