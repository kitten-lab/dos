"""Cohesive TUI help pane: cheat sheet first, expand section or topic detail.

Default surface is a short cheat sheet (not the full catalog). Players expand
a category (1–9) for a scannable list, then a code (1A) or verb (look) for
full instructions — closer to a quick reference than a manual dump.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import format as fmt
from .help_topics import (
    _HELP_INDEX_CATEGORIES,
    render_help_topic,
    resolve_index_code,
    resolve_topic,
    topic_index_entries,
)


def parse_help_command(line: str) -> str | None:
    """If *line* is a help command, return topic ('' for bare help/?); else None."""
    parts = line.strip().split(maxsplit=1)
    if not parts:
        return None
    if parts[0].lower() not in ("help", "?"):
        return None
    return parts[1].strip() if len(parts) > 1 else ""


def topic_key_for_index_term(term: str) -> str | None:
    """Map an index label like 'take / drop' to a canonical help topic key."""
    for part in re.split(r"[/,]", term):
        key = resolve_topic(part.strip())
        if key:
            return key
    return resolve_topic(term)


def numbered_index_entries() -> list[tuple[str, str, str, str]]:
    """(code, index_label, summary, topic_key) from the grouped topic list."""
    out: list[tuple[str, str, str, str]] = []
    for code, term, summary, _cat in topic_index_entries():
        key = topic_key_for_index_term(term)
        if not key:
            continue
        out.append((code, term, summary, key))
    return out


# Layout for the dense catalog (help all)
HELP_INDEX_TERM_WIDTH = 18
# Topic keys: 11, 21, … or legacy 1a
_TOPIC_CODE_RE = re.compile(r"^(\d)(\d)$")
_LEGACY_LETTER_RE = re.compile(r"^(\d+)([A-Za-z]+)$", re.IGNORECASE)


def _category_count() -> int:
    return len(_HELP_INDEX_CATEGORIES)


# Help pane ~56 cols; keep footer lines short so they don't wrap mid-phrase.
_HELP_FOOTER_RULE_W = 40
# Only the typeable key is bright — brackets stay dim (quiet chrome)
_KEY_COLOR = "bright_cyan"


def _help_rule() -> str:
    """Dim HR matching the help pane chrome (not the 72 world measure)."""
    return f"[dim]{'─' * _HELP_FOOTER_RULE_W}[/dim]"


def _key_chip(code: str) -> str:
    """Bright typeable key only — no brackets (less visual noise)."""
    c = (code or "").strip()
    return f"[bold {_KEY_COLOR}]{fmt.safe(c)}[/bold {_KEY_COLOR}]"


def _section_title_markup(section_n: int, title: str) -> str:
    """Section: bright number, plain bold title (no rainbow, no brackets)."""
    return (
        f"{_key_chip(str(section_n))}  "
        f"[bold]{fmt.safe(title)}[/bold]"
    )


def _help_nav_footer(*, context: str = "cheat") -> list[str]:
    """
    Bottom nav as short, separate lines (avoids ugly wrap in the side pane).

    0 always returns to the root cheat sheet.
    """
    return [
        "",
        _help_rule(),
        f"{_key_chip('1')}[dim]–[/dim]{_key_chip(str(_category_count()))}"
        f"  [dim]section[/dim]",
        f"{_key_chip('11')}  [dim]topic (section+item) · or type the verb[/dim]",
        f"[dim]all[/dim]   [dim]full catalog[/dim]",
        f"{_key_chip('0')}  [dim]root cheat sheet[/dim]",
        f"[dim]help / ?  close pane[/dim]",
    ]


def _normalize_code_input(raw: str) -> str:
    """Accept ``11``, ``1a``, ``[11]``, ``[1A]``."""
    s = (raw or "").strip()
    if len(s) >= 2 and s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    return s.lower()


def _coded_items_for_section(
    section_n: int, items: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """(code, label) per index entry — digit codes for rapid numpad typing."""
    from .help_topics import topic_code

    out: list[tuple[str, str]] = []
    for item_i, (term, _sum) in enumerate(items):
        code = topic_code(section_n, item_i)
        # Compact: "take / drop" → "take/drop"
        label = term.replace(" / ", "/")
        out.append((code, label))
    return out


def _coded_grid_markup(
    pairs: list[tuple[str, str]], *, cols: int = 2, col_w: int = 18
) -> list[str]:
    """
    Multi-column rows: bright key + double space + dim verb::

      11  look      12  go
      13  run       14  logout
    """
    if not pairs:
        return []
    rows: list[str] = []
    for i in range(0, len(pairs), cols):
        chunk = pairs[i : i + cols]
        cells: list[str] = []
        for code, label in chunk:
            # Two spaces between code and word (same as section sublist)
            plain_cell = f"{code}  {label}"
            pad = max(0, col_w - len(plain_cell))
            cell = (
                f"{_key_chip(code)}  "
                f"[dim]{fmt.safe(label)}[/dim]"
                + (" " * pad)
            )
            cells.append(cell)
        # Indent past section number so codes sit under the title eyeline
        # (title is "N  TITLE"; 4 spaces lines codes under the name, not the digit)
        rows.append("    " + "".join(cells).rstrip())
    return rows


def render_cheat_sheet() -> str:
    """
    Default help: section headers + coded multi-column command grid.

    Glanceable; type [1A] or look for full instructions. 0 → this root.
    """
    lines = [
        fmt.title_line("Help · cheat sheet"),
        fmt.hint("Glance list · expand a section · open one topic"),
        _help_rule(),
        "",
    ]
    for i, (cat_title, items) in enumerate(_HELP_INDEX_CATEGORIES, start=1):
        title = cat_title.upper() if cat_title != cat_title.upper() else cat_title
        lines.append(_section_title_markup(i, title))
        lines.append("")
        pairs = _coded_items_for_section(i, items)
        lines.extend(_coded_grid_markup(pairs, cols=2, col_w=22))
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    lines.extend(_help_nav_footer(context="cheat"))
    return "\n".join(lines)


def render_section(section_n: int) -> str | None:
    """Expand one category into codes + one-line summaries; None if out of range."""
    if section_n < 1 or section_n > len(_HELP_INDEX_CATEGORIES):
        return None
    cat_title, items = _HELP_INDEX_CATEGORIES[section_n - 1]
    title = cat_title.upper() if cat_title != cat_title.upper() else cat_title
    lines = [
        fmt.title_line(f"Help · {title}"),
        _section_title_markup(section_n, title),
        fmt.hint("key → full instructions"),
        _help_rule(),
        "",
    ]
    for item_i, (term, summary) in enumerate(items):
        from .help_topics import topic_code

        code = topic_code(section_n, item_i)
        # Indent past section number; double space between code and word
        lines.append(
            f"    {_key_chip(code)}  [dim]{fmt.safe(term)}[/dim]"
        )
        lines.append(f"        [dim]{fmt.safe(summary)}[/dim]")
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    lines.extend(_help_nav_footer(context="section"))
    return "\n".join(lines)


def render_numbered_index() -> str:
    """Full catalog (help all) — denser; not the default open."""
    lines = [
        fmt.title_line("Help · full catalog"),
        fmt.hint("key → topic"),
        _help_rule(),
        "",
    ]
    current_cat: str | None = None
    current_n = 0
    for code, term, summary, cat in topic_index_entries():
        key = topic_key_for_index_term(term)
        if not key:
            continue
        if cat != current_cat:
            if current_cat is not None:
                lines.append("")
            cat_num = "".join(ch for ch in code if ch.isdigit()) or "0"
            current_n = int(cat_num) if cat_num.isdigit() else 0
            title = cat.upper() if cat != cat.upper() else cat
            lines.append(_section_title_markup(current_n, title))
            current_cat = cat
        term_s = (
            term
            if len(term) <= HELP_INDEX_TERM_WIDTH
            else term[: HELP_INDEX_TERM_WIDTH - 1] + "…"
        )
        lines.append(
            f"    {_key_chip(code)}  [dim]{fmt.safe(term_s)}[/dim]"
        )
        lines.append(f"        [dim]{fmt.safe(summary)}[/dim]")
    lines.extend(_help_nav_footer(context="catalog"))
    return "\n".join(lines)


def render_help_body(topic: str = "") -> str:
    """Content for the help pane (cheat / section / topic / full catalog)."""
    if not topic:
        return render_cheat_sheet()
    if topic == "__catalog__":
        return render_numbered_index()
    if topic.startswith("__section__:"):
        try:
            n = int(topic.split(":", 1)[1])
        except ValueError:
            return render_cheat_sheet()
        body = render_section(n)
        return body if body else render_cheat_sheet()
    detail = render_help_topic(topic)
    return detail + "\n" + "\n".join(_help_nav_footer(context="topic"))


@dataclass
class HelpRoute:
    """Result of routing a TUI input line through the help pane."""

    handled: bool
    """True if the line was consumed by help (do not dispatch as world cmd)."""
    refresh_help: bool = False
    """True if the help pane body should be re-rendered."""
    log_message: str | None = None
    """Optional short world-log note only — never full help body."""
    world_line: str | None = None
    """If set, dispatch this as a normal world command (help stays open)."""


@dataclass
class HelpPane:
    """
    Single TUI help surface state.

    Modes:
      cheat   — default glance sheet (category one-liners)
      section — one category expanded
      catalog — full coded index (help all)
      topic   — full topic instructions
    """

    open: bool = False
    mode: str = "cheat"  # cheat | section | catalog | topic
    topic_key: str = ""
    section_n: int = 0

    def body(self) -> str:
        if not self.open:
            return ""
        if self.mode == "topic" and self.topic_key:
            return render_help_body(self.topic_key)
        if self.mode == "section" and self.section_n:
            return render_help_body(f"__section__:{self.section_n}")
        if self.mode == "catalog":
            return render_help_body("__catalog__")
        return render_help_body("")

    def open_cheat(self) -> None:
        self.open = True
        self.mode = "cheat"
        self.topic_key = ""
        self.section_n = 0

    def open_index(self) -> None:
        """Back-compat: open default surface (cheat sheet)."""
        self.open_cheat()

    def open_catalog(self) -> None:
        self.open = True
        self.mode = "catalog"
        self.topic_key = ""
        self.section_n = 0

    def open_section(self, n: int) -> bool:
        if n < 1 or n > _category_count():
            return False
        self.open = True
        self.mode = "section"
        self.section_n = n
        self.topic_key = ""
        return True

    def open_topic(self, key: str) -> bool:
        resolved = resolve_topic(key) if key else None
        if not resolved:
            resolved = resolve_index_code(key) if key else None
        if not resolved:
            return False
        self.open = True
        self.mode = "topic"
        self.topic_key = resolved
        return True

    def close(self) -> None:
        self.open = False
        self.mode = "cheat"
        self.topic_key = ""
        self.section_n = 0

    def select_number(self, n: int) -> bool:
        """Open topic by legacy 1-based flat position (first entry = 1)."""
        entries = numbered_index_entries()
        if 1 <= n <= len(entries):
            _code, _term, _summary, key = entries[n - 1]
            return self.open_topic(key)
        return False

    def select_code(self, code: str) -> bool:
        """Open topic by digit code ``11`` or legacy ``1a``."""
        raw = _normalize_code_input(code)
        key = resolve_index_code(raw)
        if key:
            # Remember section from first digit when possible
            if raw and raw[0].isdigit():
                self.section_n = int(raw[0])
            return self.open_topic(key)
        return False

    def _open_item_in_section(self, section_n: int, item_n: int) -> bool:
        """item_n is 1-based within section."""
        if section_n < 1 or section_n > len(_HELP_INDEX_CATEGORIES):
            return False
        items = _HELP_INDEX_CATEGORIES[section_n - 1][1]
        if item_n < 1 or item_n > len(items):
            return False
        key = topic_key_for_index_term(items[item_n - 1][0])
        if not key:
            return False
        self.section_n = section_n
        return self.open_topic(key)

    def go_back(self) -> None:
        """Prefer root cheat sheet (0 always roots; back may step once)."""
        self.open_cheat()

    def go_index(self) -> None:
        """Back-compat name: return to cheat sheet."""
        self.open_cheat()

    def handle_line(self, line: str) -> HelpRoute:
        """
        Route a TUI command line.

        - help / ? : toggle pane (open cheat; open → close)
        - help all : full catalog
        - while open:
            0 → root cheat
            1–9 → section (or item N if already in a section)
            11 / 21 → topic (section+item, numpad-fast)
            1a → still works (legacy)
        """
        raw = line.strip()
        if not raw:
            return HelpRoute(handled=True)

        if self.open:
            low = raw.lower()
            # 0 and root synonyms → always cheat sheet
            if low in ("0", "cheat", "home", "menu", "sheet", "root"):
                self.open_cheat()
                return HelpRoute(handled=True, refresh_help=True)
            if low == "back":
                if self.mode == "topic" and self.section_n:
                    self.mode = "section"
                    self.topic_key = ""
                else:
                    self.open_cheat()
                return HelpRoute(handled=True, refresh_help=True)

            if low in ("all", "index", "catalog", "full"):
                self.open_catalog()
                return HelpRoute(handled=True, refresh_help=True)

            if raw.isdigit():
                n = int(raw)
                if n == 0:
                    self.open_cheat()
                    return HelpRoute(handled=True, refresh_help=True)
                # Two digits: 11 = section 1 item 1 (fast topic jump)
                if len(raw) == 2:
                    sec, item = int(raw[0]), int(raw[1])
                    if sec >= 1 and item >= 1 and self._open_item_in_section(sec, item):
                        return HelpRoute(handled=True, refresh_help=True)
                    return HelpRoute(handled=True, refresh_help=False)
                # One digit: in a section → pick item; else open section
                if len(raw) == 1:
                    if self.mode == "section" and self.section_n:
                        if self._open_item_in_section(self.section_n, n):
                            return HelpRoute(handled=True, refresh_help=True)
                    if self.open_section(n):
                        return HelpRoute(handled=True, refresh_help=True)
                    return HelpRoute(handled=True, refresh_help=False)
                return HelpRoute(handled=True, refresh_help=False)

            code_in = _normalize_code_input(raw)
            if _TOPIC_CODE_RE.fullmatch(code_in) or _LEGACY_LETTER_RE.fullmatch(
                code_in
            ):
                if self.select_code(code_in):
                    return HelpRoute(handled=True, refresh_help=True)
                return HelpRoute(handled=True, refresh_help=False)

        help_arg = parse_help_command(raw)
        if help_arg is not None:
            if help_arg == "":
                if self.open:
                    self.close()
                    return HelpRoute(handled=True, refresh_help=True)
                self.open_cheat()
                return HelpRoute(handled=True, refresh_help=True)
            low_arg = help_arg.lower()
            if low_arg in ("all", "index", "catalog", "full"):
                self.open_catalog()
                return HelpRoute(handled=True, refresh_help=True)
            if low_arg in ("cheat", "sheet", "home", "root", "0"):
                self.open_cheat()
                return HelpRoute(handled=True, refresh_help=True)
            if help_arg.isdigit():
                n = int(help_arg)
                if n == 0:
                    self.open_cheat()
                    return HelpRoute(handled=True, refresh_help=True)
                if len(help_arg) == 2:
                    sec, item = int(help_arg[0]), int(help_arg[1])
                    if self._open_item_in_section(sec, item):
                        return HelpRoute(handled=True, refresh_help=True)
                if len(help_arg) == 1 and self.open_section(n):
                    return HelpRoute(handled=True, refresh_help=True)
            code_in = _normalize_code_input(help_arg)
            if self.select_code(code_in) or self.open_topic(help_arg):
                return HelpRoute(handled=True, refresh_help=True)
            self.open_cheat()
            return HelpRoute(handled=True, refresh_help=True)

        return HelpRoute(handled=False, world_line=raw)


# Back-compat aliases used by older imports/tests
HelpSidebarState = HelpPane


def render_help_body_compat(topic: str = "") -> str:
    return render_help_body(topic)
