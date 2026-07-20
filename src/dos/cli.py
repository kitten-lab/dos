"""CLI and Textual entrypoints."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from . import PRODUCT_NAME, format as fmt
from .commands import dispatch
from .db import connect, get_meta, init_schema, migrate_schema
from .help_ui import HelpPane
from .history import CommandHistory
from .seed import seed_world
from .status import format_strip
from .world import World

DEFAULT_WORLD = Path(__file__).resolve().parents[2] / "worlds" / "seed.world.db"
console = Console(highlight=False)

# TUI chrome (exported for tests) — darker surfaces, sharp solid borders, wide help
TUI_HELP_PANE_WIDTH = 56
TUI_HELP_PANE_MIN_WIDTH = 48
TUI_HELP_PANE_MAX_WIDTH = 72
# Book reader is a soft full-width modal (phase 2); no side-rail width tokens
TUI_BG = "#0a0a0c"
TUI_SURFACE = "#0e0e12"
TUI_PANEL = "#121218"
TUI_BORDER = "#3d3d48"
TUI_BORDER_ACCENT = "#5ec8d8"
TUI_INPUT_BG = "#0c0c10"


def ensure_world(path: Path, reseed: bool = False, seed: str = "office") -> World:
    if reseed and path.exists():
        path.unlink()
    is_new = not path.exists()
    conn = connect(path)
    if is_new or reseed:
        seed_world(conn, flavor=seed)
        console.print(fmt.hint(f"Seeded world ({seed}) · {path}"))
    else:
        init_schema(conn)
        migrate_schema(conn)
    return World(conn)


def _is_desc_multiline_start(line: str) -> bool:
    parts = line.strip().split(maxsplit=1)
    if not parts or parts[0].lower() != "@desc":
        return False
    if len(parts) < 2:
        return False
    rest = parts[1].strip().lower()
    # @desc <<  ·  @desc <<studio  ·  @desc on x <<studio
    if rest in ("<<", "{", "<<studio", "{studio"):
        return True
    if rest.endswith("<<") or rest.endswith("<<studio"):
        return True
    return False


def _desc_multiline_studio(line: str) -> bool:
    """Whether multiline @desc should store Studio Text."""
    low = line.strip().lower()
    return "studio" in low and ("<<" in low or "{" in low)


def _is_book_page_multiline_start(line: str) -> bool:
    """folio|book page|leaf add|edit … << or <<studio"""
    low = line.strip().lower()
    for prefix in ("book page ", "folio page ", "book leaf ", "folio leaf "):
        if low.startswith(prefix):
            return "<<" in low
    return False


def _book_page_multiline_studio(line: str) -> bool:
    low = line.strip().lower()
    return "studio" in low and "<<" in low


def _parse_book_page_multiline_start(line: str) -> dict | None:
    """
    Parse folio/book page multiline opener.

    folio page add <name> <title> <<studio
    book page add <name> <<studio          → title empty
    folio leaf edit <name> <n> <<studio
    """
    s = line.strip()
    low = s.lower()
    prefix = None
    for p in ("book page ", "folio page ", "book leaf ", "folio leaf "):
        if low.startswith(p):
            prefix = p
            break
    if prefix is None:
        return None
    rest = s[len(prefix) :].strip()
    for end in ("<<studio", "<<"):
        if rest.lower().endswith(end):
            rest = rest[: -len(end)].strip()
            break
    else:
        return None
    parts = rest.split(maxsplit=1)
    if not parts:
        return None
    action = parts[0].lower()
    if action not in ("add", "append", "edit", "set", "body"):
        return None
    tail = parts[1].strip() if len(parts) > 1 else ""
    studio = _book_page_multiline_studio(line)
    if action in ("edit", "set", "body"):
        tokens = tail.split()
        page_i = None
        page_val = None
        for i, tok in enumerate(tokens):
            if tok.isdigit():
                page_i = i
                page_val = int(tok)
                break
        if page_i is None or page_val is None:
            return None
        book_name = " ".join(tokens[:page_i]).strip()
        if not book_name:
            return None
        return {
            "action": "edit",
            "book_name": book_name,
            "page": page_val,
            "studio": studio,
        }
    return {
        "action": "add",
        "book_and_title": tail,
        "studio": studio,
    }


def _book_page_collect_hint(*, studio: bool) -> str:
    base = "Multiline book page"
    if studio:
        base += " (studio text · chapter section)"
    return (
        f"{base} — each line shown as added (logical lines; wrap doesn't renumber).  "
        f"undo / u = last line.  End with .  or >>"
    )


def _commit_book_page_multiline(
    world: World,
    meta: dict,
    body: str,
) -> str:
    """Build dispatch line after multiline collect; return command string.

    Body from ``MultilineDescDraft`` uses real newlines. Book parsers tokenize
    with ``str.split()``, so newlines must be escaped to ``\\n`` here; store
    path runs ``unescape_desc`` and restores logical lines for numbering.
    """
    from .textutil import escape_desc

    studio = bool(meta.get("studio"))
    body = escape_desc(body or "")
    if meta.get("action") == "edit":
        book_name = meta["book_name"]
        page = meta["page"]
        if studio:
            return f"book page edit {book_name} {page} studio | {body}"
        return f"book page edit {book_name} {page} {body}"
    # add: book_and_title is "book… [title words]"
    book_and_title = (meta.get("book_and_title") or "").strip()
    if not book_and_title:
        title = "Untitled"
        # need book from context — fail at dispatch
        if studio:
            return f"book page add | {title} | studio | {body}"
        return f"book page add | {title} | {body}"
    # Split book vs title with world at call site preferred — use greedy split in dispatch
    # Store as: book page add <book_and_title> with content as studio body
    # Parse: title is last word group if multi-word book... use content as body with title from tail
    # Commit form that parse_lore_add understands after book split:
    # book page add <book> Title | studio | body  OR book page add <book> | Title | studio | body
    if studio:
        # title may be multi-word after book name — leave as "tokens" and let command split
        return f"book page add {book_and_title} | studio | {body}"
    return f"book page add {book_and_title} | {body}"


# End multiline collection
_DESC_END_MARKERS = frozenset({".", ">>", "}"})
# During collection: pop only the last accepted draft line
_DESC_UNDO_TOKENS = frozenset({"undo", "u", "/undo", "-u"})


class MultilineDescDraft:
    """
    In-progress @desc << body: accept lines, undo last line, join on end.

    Pure buffer so REPL/TUI and tests share one path (no parallel reimplementation).
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __len__(self) -> int:
        return len(self.lines)

    def accept(self, line: str) -> None:
        """Append one content line (trailing newline already stripped by caller)."""
        self.lines.append(line)

    def undo_last(self) -> str | None:
        """Remove and return the last content line, or None if draft is empty."""
        if not self.lines:
            return None
        return self.lines.pop()

    def body(self) -> str | None:
        """Joined draft, or None if empty/whitespace-only (cancel)."""
        joined = "\n".join(self.lines)
        return joined if joined.strip() else None

    def feed(self, raw: str) -> str:
        """
        Process one input line during collection.

        Returns one of:
          ``accepted`` — content line stored (caller should echo)
          ``undone`` — last line removed (caller may show status)
          ``empty_undo`` — undo with nothing to pop
          ``done`` — end marker; body available via ``body()``
          ``cancel`` — end marker with empty draft
        """
        s = raw.rstrip("\n\r")
        stripped = s.strip()
        low = stripped.lower()
        if stripped in _DESC_END_MARKERS:
            return "done" if self.body() is not None else "cancel"
        if low in _DESC_UNDO_TOKENS:
            if self.undo_last() is None:
                return "empty_undo"
            return "undone"
        self.accept(s)
        return "accepted"


def _collect_multiline_desc(
    read_line,
    *,
    on_accepted=None,
    on_undone=None,
    on_empty_undo=None,
    history: CommandHistory | None = None,
) -> str | None:
    """
    Read lines until end marker. Echo/undo via optional callbacks.

    ``on_accepted(line, draft)`` — after each content line is stored.
    ``on_undone(removed, draft)`` — after last-line undo.
    ``on_empty_undo(draft)`` — undo when draft has no lines.
    ``history`` — when set, each accepted content line is pushed for up/down
    recall (studio and plain multiline). End markers / undo tokens are not pushed.

    Returns joined body or None if cancelled empty.
    """
    draft = MultilineDescDraft()
    while True:
        try:
            raw = read_line()
        except (EOFError, KeyboardInterrupt):
            break
        action = draft.feed(raw)
        if action == "accepted":
            text = draft.lines[-1]
            if history is not None:
                history.push_content_line(text)
            if on_accepted is not None:
                on_accepted(text, draft)
        elif action == "undone":
            if on_undone is not None:
                # removed line already popped; report count remaining
                on_undone(draft)
        elif action == "empty_undo":
            if on_empty_undo is not None:
                on_empty_undo(draft)
        elif action == "done":
            return draft.body()
        elif action == "cancel":
            return None
    return draft.body()


def _desc_collect_hint(*, studio: bool = False) -> str:
    base = "Multiline @desc"
    if studio:
        base += " (studio text)"
    return (
        f"{base} — each line is shown as added.  "
        f"undo / u = drop last line.  "
        f"End with a line containing only .  (or >>)"
    )


def _world_chrome_label(world_path: Path) -> str:
    """Window / banner file identity — path name, not seed flavor (e.g. The Void)."""
    return world_path.name or str(world_path)


def _dos_logo_markup() -> str:
    """Cute header badge: white DOS on cyan pill."""
    return "[bold white on #5ec8d8] DOS [/]"


def _studio_boot_banner_markup(world_path: Path, world_name: str) -> str:
    """Log-only tips after clear/mount (identity lives in the persistent header bar)."""
    _ = world_path, world_name
    return (
        f"[dim]help / ? or F1 = help pane  ·  folio open = reader (←/→ · + leaf · e edit)[/dim]\n"
        f"[dim]↑ / ↓ previous commands · locate self · clear / clr[/dim]\n"
    )


def _studio_boot_panel(world_path: Path, world_name: str) -> Panel:
    """Rich panel for plain REPL boot / clear."""
    _ = world_name
    file_label = _world_chrome_label(world_path)
    return Panel(
        f"{_dos_logo_markup()}  [dim]{fmt.safe(file_label)}[/dim]\n\n"
        f"[dim]try[/dim]    look · locate self · undo · help · clear\n"
        f"[dim]↑[/dim]       previous commands  ·  "
        f"[dim]tui[/dim]  python -m dos --textual",
        border_style="dim",
        padding=(1, 2),
        title="[bright_cyan]dos[/bright_cyan]",
        title_align="left",
    )


def _clear_repl_screen(
    world_path: Path | None = None,
    world_name: str | None = None,
    *,
    restore_banner: bool = False,
) -> None:
    """Best-effort clear for plain REPL. Banner only if restore_banner (boot)."""
    import os
    import sys

    # Windows terminals often support ANSI; fall back to newlines
    try:
        if os.name == "nt":
            os.system("cls")
        else:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
    except OSError:
        console.print("\n" * 40)
    if (
        restore_banner
        and world_path is not None
        and world_name is not None
    ):
        console.print()
        console.print(_studio_boot_panel(world_path, world_name))
        console.print()


def run_repl(world: World, world_path: Path) -> None:
    name = get_meta(world.conn, "world_name", world_path.name) or world_path.name
    console.print()
    console.print(_studio_boot_panel(world_path, name))
    console.print()

    r = dispatch(world, "look")
    if r.message:
        console.print(r.message)
        console.print()

    history = CommandHistory()
    session = None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.history import InMemoryHistory

        class _LinkedPtkHistory(InMemoryHistory):
            """prompt_toolkit up/down shares CommandHistory (incl. studio lines)."""

            def store_string(self, string: str) -> None:  # type: ignore[override]
                super().store_string(string)
                history.push(string)

        ptk_history = _LinkedPtkHistory()
        session = PromptSession(history=ptk_history)
    except ImportError:
        session = None

    def read_prompt(prefix: str = "›") -> str:
        if session is not None:
            from prompt_toolkit.formatted_text import HTML

            return session.prompt(HTML(f"<ansicyan><b>{prefix}</b></ansicyan> "))
        return console.input(f"[bright_cyan]{prefix}[/bright_cyan] ")

    while True:
        console.print(Rule(style="dim"))
        console.print(format_strip(world))
        try:
            line = read_prompt("›")
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print(fmt.hint("Bye."))
            break

        # Without prompt_toolkit, read_prompt does not store; keep CommandHistory filled.
        # With ptk, store_string already pushed (consecutive dup is a no-op).
        history.push(line)

        # << / <<studio → nano-like buffer editor (desc, book page, lore)
        from .multiline_open import (
            commit_multiline_session,
            parse_multiline_opener,
            seed_initial_body,
            seed_page_title,
        )
        from .text_editor import run_text_editor

        ml = parse_multiline_opener(line)
        if ml is not None:
            console.print(
                fmt.hint(
                    f"Opening editor · {ml.title}  ·  Ctrl+S save  ·  Esc / Ctrl+Q cancel"
                )
            )
            initial = seed_initial_body(world, ml)
            page_title = seed_page_title(world, ml)
            edited = run_text_editor(
                initial=initial,
                title=ml.title,
                studio=ml.studio,
                page_title=page_title,
            )
            if edited is None:
                console.print()
                console.print(fmt.hint("Editor cancelled."))
                console.print(fmt.turn_separator())
                continue
            result = commit_multiline_session(
                world,
                ml,
                edited.body,
                page_title=edited.page_title,
            )
            if result.clear_log:
                _clear_repl_screen(world_path, name)
            if result.message:
                console.print()  # blank after command / editor before result
                console.print(result.message)
                console.print(fmt.turn_separator())
            elif not result.clear_log:
                console.print(fmt.turn_separator())
            if result.quit:
                break
            continue

        result = dispatch(world, line)
        if result.clear_log:
            _clear_repl_screen(world_path, name)
        if result.message:
            console.print()  # blank after typed command before result
            console.print(result.message)
            console.print(fmt.turn_separator())
        elif not result.clear_log:
            console.print(fmt.turn_separator())
        if result.quit:
            break


def run_textual(world: World, world_path: Path) -> None:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Footer, Input, RichLog, Static

    from .book_ui import make_book_reader_screen
    from .wiki_ui import make_wiki_reader_screen
    from .history import CommandHistory

    class HistoryInput(Input):
        """Input with ↑ / ↓ command history."""

        BINDINGS = [
            Binding("up", "hist_up", "Prev cmd", show=False, priority=True),
            Binding("down", "hist_down", "Next cmd", show=False, priority=True),
        ]

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.cmd_history = CommandHistory()

        def action_hist_up(self) -> None:
            nxt = self.cmd_history.up(self.value)
            if nxt is not None:
                self.value = nxt
                self.cursor_position = len(self.value)

        def action_hist_down(self) -> None:
            nxt = self.cmd_history.down(self.value)
            if nxt is not None:
                self.value = nxt
                self.cursor_position = len(self.value)

    class StudioApp(App[None]):
        """World log + help side rail; book open uses a soft full-width reader modal."""

        def action_open_url(self, url: str) -> None:
            """Open an external http(s) link from studio text (clickable @click)."""
            from .studio_text import is_openable_url

            u = (url or "").strip()
            if is_openable_url(u):
                self.open_url(u)

        # Sharp/dark chrome: solid borders, near-black panels, wider help rail
        CSS = f"""
        Screen {{
            background: {TUI_BG};
        }}
        #body {{
            height: 1fr;
            background: {TUI_BG};
        }}
        #log {{
            width: 1fr;
            height: 1fr;
            border: solid {TUI_BORDER};
            padding: 1 2;
            background: {TUI_SURFACE};
            color: #e8e8ec;
            scrollbar-background: {TUI_BG};
            scrollbar-color: {TUI_BORDER};
        }}
        #help-pane {{
            width: {TUI_HELP_PANE_WIDTH};
            min-width: {TUI_HELP_PANE_MIN_WIDTH};
            max-width: {TUI_HELP_PANE_MAX_WIDTH};
            height: 1fr;
            border: solid {TUI_BORDER_ACCENT};
            padding: 1 2;
            background: {TUI_PANEL};
            color: #e8e8ec;
            scrollbar-background: {TUI_BG};
            scrollbar-color: {TUI_BORDER};
        }}
        #help-pane.help-hidden {{
            display: none;
            width: 0;
            min-width: 0;
            max-width: 0;
            padding: 0;
            border: none;
        }}
        #help-pane-title {{
            padding-bottom: 1;
            height: auto;
            border-bottom: solid {TUI_BORDER};
            margin-bottom: 1;
        }}
        #help-pane-scroll {{
            height: 1fr;
            background: {TUI_PANEL};
        }}
        #help-pane-body {{
            height: auto;
            background: {TUI_PANEL};
        }}
        #cmd {{
            dock: bottom;
            margin: 0 0;
            border: solid {TUI_BORDER_ACCENT};
            background: {TUI_INPUT_BG};
            color: #e8e8ec;
            padding: 0 1;
        }}
        #studio-header {{
            dock: top;
            height: 3;
            background: {TUI_PANEL};
            border-bottom: solid {TUI_BORDER_ACCENT};
            padding: 0 1;
            layout: horizontal;
        }}
        #header-left, #header-center, #header-right {{
            height: 3;
            content-align: center middle;
            color: #c8c8d0;
        }}
        #header-left {{
            width: auto;
            min-width: 7;
            content-align: left middle;
            color: #e8e8ec;
            padding: 0 1 0 0;
        }}
        #header-center {{
            width: 1fr;
            content-align: left middle;
            color: #888890;
        }}
        #header-right {{
            width: auto;
            min-width: 12;
            content-align: right middle;
            color: #5ec8d8;
        }}
        Footer {{
            background: {TUI_BG};
            color: #888890;
            border-top: solid {TUI_BORDER};
        }}
        """
        BINDINGS = [
            Binding("ctrl+c", "quit", "Quit"),
            Binding("f1", "toggle_help", "Help"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.help_pane = HelpPane(open=False)
            self._turn = 0
            self._open_book_id: str | None = None
            self._open_wiki: tuple[str, bool] | None = None

        def compose(self) -> ComposeResult:
            with Horizontal(id="studio-header"):
                yield Static("", id="header-left", markup=True)
                yield Static("", id="header-center", markup=True)
                yield Static("", id="header-right", markup=True)
            with Horizontal(id="body"):
                yield RichLog(
                    id="log",
                    highlight=False,
                    markup=True,
                    wrap=True,
                    auto_scroll=True,
                )
                with Vertical(id="help-pane", classes="help-hidden"):
                    yield Static(
                        f"[bold {fmt.ACCENT}]help[/bold {fmt.ACCENT}]  "
                        f"[dim]numbers open topics · 0 index · help/? close[/dim]",
                        id="help-pane-title",
                        markup=True,
                    )
                    with VerticalScroll(id="help-pane-scroll"):
                        yield Static(id="help-pane-body", markup=True)
            yield HistoryInput(
                placeholder="look  ·  book open  ·  help / ?  ·  ↑↓ history",
                id="cmd",
            )
            yield Footer()

        def on_mount(self) -> None:
            name = get_meta(world.conn, "world_name", world_path.name) or world_path.name
            # OS window chrome — short product slug
            file_label = _world_chrome_label(world_path)
            self.title = f"DOS | {file_label}"
            self.sub_title = ""
            self._refresh_studio_header()
            self._refresh_help_pane()
            log = self.query_one("#log", RichLog)
            log.write(_studio_boot_banner_markup(world_path, name))
            r = dispatch(world, "look")
            if r.message:
                log.write(r.message)
            log.write(fmt.turn_separator())
            self._refresh_studio_header()
            self.query_one("#cmd", HistoryInput).focus()

        def _refresh_studio_header(self) -> None:
            """
            Persistent top bar:
              left   DOS logo (white on cyan)
              center (open — no seed chrome)
              right  current location
            """
            from .ids import display_name

            loc = world.player_location()
            loc_name = display_name(loc.name) if loc else "—"

            left = self.query_one("#header-left", Static)
            center = self.query_one("#header-center", Static)
            right = self.query_one("#header-right", Static)
            left.update(_dos_logo_markup())
            center.update("")
            right.update(f"[dim]@[/dim] {fmt.safe(loc_name)}")

        def _close_help_only(self) -> None:
            if self.help_pane.open:
                self.help_pane.open = False
                self._refresh_help_pane()

        def _book_reader_is_top(self) -> bool:
            """True when a soft reader (folio or wiki) is the top modal."""
            scr = self.screen
            return bool(getattr(scr, "IS_BOOK_READER", False)) or bool(
                getattr(scr, "IS_WIKI_READER", False)
            )

        def _close_book_reader(self) -> None:
            """Dismiss soft reader modal (folio or wiki) if open."""
            if (
                self._open_book_id is None
                and self._open_wiki is None
                and not self._book_reader_is_top()
            ):
                return
            self._open_book_id = None
            self._open_wiki = None
            if self._book_reader_is_top():
                self.pop_screen()

        def _refresh_help_pane(self) -> None:
            pane = self.query_one("#help-pane", Vertical)
            body = self.query_one("#help-pane-body", Static)
            if self.help_pane.open:
                # Mutual exclusion: help closes the soft reader
                if (
                    self._open_book_id is not None
                    or self._open_wiki is not None
                    or self._book_reader_is_top()
                ):
                    self._close_book_reader()
                pane.remove_class("help-hidden")
                body.update(self.help_pane.body())
            else:
                pane.add_class("help-hidden")
                body.update("")

        def _open_book_reader(self, book_instance_id: str) -> None:
            """Push soft full-width book reader (replaces prior side rail)."""
            self._close_help_only()
            # One soft reader at a time
            if self._book_reader_is_top():
                self.pop_screen()
            self._open_wiki = None
            self._open_book_id = book_instance_id
            screen = make_book_reader_screen(world, book_instance_id, page_index=0)

            def _on_reader_closed(_result: None = None) -> None:
                self._open_book_id = None
                try:
                    self.query_one("#cmd", HistoryInput).focus()
                except Exception:  # noqa: BLE001
                    pass

            self.push_screen(screen, _on_reader_closed)

        def _open_wiki_reader(self, label: str, *, deep: bool = False) -> None:
            """Push soft full-width wiki dossier (same frame language as folio)."""
            self._close_help_only()
            if self._book_reader_is_top():
                self.pop_screen()
            self._open_book_id = None
            self._open_wiki = (label, deep)
            screen = make_wiki_reader_screen(world, label, deep=deep)

            def _on_wiki_closed(_result: None = None) -> None:
                self._open_wiki = None
                try:
                    self.query_one("#cmd", HistoryInput).focus()
                except Exception:  # noqa: BLE001
                    pass

            self.push_screen(screen, _on_wiki_closed)

        def action_toggle_help(self) -> None:
            route = self.help_pane.handle_line("help")
            if route.refresh_help:
                self._refresh_help_pane()

        def _clear_world_log(self, log: RichLog) -> None:
            """Wipe transcript only — no tips banner (clr wants a blank log)."""
            log.clear()
            self._turn = 0

        def _write_world_turn(
            self,
            log: RichLog,
            line: str,
            message: str | None,
            *,
            clear_log: bool = False,
        ) -> None:
            """World log only — never full help manuals."""
            if clear_log:
                self._clear_world_log(log)
            # Pure clear/clr: blank log, no › echo, no separator
            if clear_log and not (message or "").strip():
                self._refresh_studio_header()
                return
            if self._turn > 0:
                # One compact rule line only — no blank-line padding around it
                log.write(fmt.turn_separator())
            self._turn += 1
            log.write(f"[bright_cyan]›[/bright_cyan] {fmt.safe(line)}")
            # One empty line between command echo and result (lists, look, paths, …)
            if message:
                log.write("")
                log.write(message)
            # Location (and any seed/file chrome) stay current after go / rename / …
            self._refresh_studio_header()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            log = self.query_one("#log", RichLog)
            cmd = self.query_one("#cmd", HistoryInput)
            line = event.value.strip()
            event.input.value = ""
            if not line:
                return

            # << / <<studio → buffer editor screen (desc, book page, lore)
            from .multiline_open import (
                commit_multiline_session,
                parse_multiline_opener,
                seed_initial_body,
                seed_page_title,
            )
            from .text_editor import StudioBufferResult, make_studio_buffer_screen

            ml = parse_multiline_opener(line)
            if ml is not None:
                cmd.cmd_history.push(line)
                # Do not write a partial turn here. The modal is the feedback;
                # one full turn (HR + › + result) is emitted when the editor
                # closes — save or cancel — so the log stays consistent.
                initial = seed_initial_body(world, ml)
                page_title = seed_page_title(world, ml)
                screen = make_studio_buffer_screen(
                    initial=initial,
                    title=ml.title,
                    studio=ml.studio,
                    page_title=page_title,
                )

                def _on_editor_done(edited: StudioBufferResult | None) -> None:
                    if edited is None:
                        self._write_world_turn(
                            log,
                            line,
                            fmt.hint("Editor cancelled."),
                        )
                    else:
                        result = commit_multiline_session(
                            world,
                            ml,
                            edited.body,
                            page_title=edited.page_title,
                        )
                        self._write_world_turn(
                            log,
                            line,
                            result.message or None,
                            clear_log=result.clear_log,
                        )
                        if result.open_book_id:
                            self._open_book_reader(result.open_book_id)
                        if result.open_wiki:
                            q, deep = result.open_wiki
                            self._open_wiki_reader(q, deep=deep)
                        if result.quit:
                            self.exit()
                            return
                    try:
                        self.query_one("#cmd", HistoryInput).focus()
                    except Exception:  # noqa: BLE001
                        pass

                self.push_screen(screen, _on_editor_done)
                return

            cmd.cmd_history.push(line)

            # Single help surface: open/nav stays out of the world log
            route = self.help_pane.handle_line(line)
            if route.handled:
                if route.refresh_help:
                    self._refresh_help_pane()
                # Intentionally do not write help bodies (or even short notes) to #log
                return

            world_line = route.world_line or line
            result = dispatch(world, world_line)
            # Short note when opening soft reader (full page lives in the modal)
            if result.open_book_id:
                self._write_world_turn(
                    log,
                    world_line,
                    fmt.hint(
                        "Book open  ·  ←/→ leaves  ·  + add  ·  e edit  ·  Esc close"
                    ),
                    clear_log=result.clear_log,
                )
                self._open_book_reader(result.open_book_id)
            elif result.open_wiki:
                q, deep = result.open_wiki
                self._write_world_turn(
                    log,
                    world_line,
                    fmt.hint(
                        "Wiki open  ·  scroll  ·  Esc close"
                        + ("  ·  deep" if deep else "")
                    ),
                    clear_log=result.clear_log,
                )
                self._open_wiki_reader(q, deep=deep)
            else:
                self._write_world_turn(
                    log,
                    world_line,
                    result.message or None,
                    clear_log=result.clear_log,
                )
            if result.quit:
                self.exit()

    StudioApp().run()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dos",
        description="VEN-based MUD-like multiverse world-building studio",
    )
    p.add_argument(
        "--world",
        type=Path,
        default=DEFAULT_WORLD,
        help=f"Path to world SQLite file (default: {DEFAULT_WORLD})",
    )
    p.add_argument(
        "--reseed",
        action="store_true",
        help="Delete and recreate the world from the office seed",
    )
    p.add_argument(
        "--seed",
        choices=("office", "empty", "bootstrap"),
        default="office",
        help=(
            "Seed flavor when creating/reseeding: office (default company campus), "
            "empty (unfurnished suite), or bootstrap (bare Herenow for kernel tests)"
        ),
    )
    p.add_argument(
        "--textual",
        action="store_true",
        help="Launch Textual TUI (help bar toggled with help / ?)",
    )
    p.add_argument(
        "--command",
        "-c",
        action="append",
        default=[],
        help="Run a command non-interactively (repeatable), then exit",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    world = ensure_world(args.world, reseed=args.reseed, seed=args.seed)

    if args.command:
        for i, c in enumerate(args.command):
            result = dispatch(world, c)
            if result.message:
                if i > 0:
                    console.print()
                console.print(result.message)
            if not result.ok:
                sys.exit(1)
            if result.quit:
                break
        return

    if args.textual:
        run_textual(world, args.world)
    else:
        run_repl(world, args.world)


if __name__ == "__main__":
    main()
