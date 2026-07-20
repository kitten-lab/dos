"""Standalone help CLI — open in a second terminal beside Digital Office Spaces.

No world DB, no play session. Same topic catalog as in-game help.

Examples::

    dos-help              # Textual display (TTY)
    dos-help look         # Textual opened on topic
    dos-help --print look # one-shot plain print (scripts)
    dos-help -i           # line-mode interactive
    python -m dos.help_cli
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, TextIO

from rich.console import Console

from . import PRODUCT_NAME, format as fmt
from .help_topics import render_help_topic, resolve_index_code
from .help_ui import (
    numbered_index_entries,
    render_help_body,
    render_numbered_index,
)

# Simple dark chrome (standalone help TUI — exported for tests)
HELP_TUI_BG = "#0a0a0c"
HELP_TUI_SURFACE = "#0e0e12"
HELP_TUI_PANEL = "#121218"
HELP_TUI_BORDER = "#3d3d48"
HELP_TUI_ACCENT = "#5ec8d8"
HELP_TUI_INPUT_BG = "#0c0c10"


def help_text_for_query(query: str = "") -> str:
    """
    Resolve a help query to markup body (shipped catalog).

    Empty / ``index`` → numbered index (same catalog as TUI help).
    Digit → topic by number from that index.
    Otherwise → topic detail via ``render_help_topic``.
    """
    q = (query or "").strip()
    if not q or q.lower() in ("index", "list", "topics", "?"):
        return render_numbered_index()
    if q.isdigit():
        # Prefer numpad codes (11 = look, 21 = inv, …) over flat position
        by_code = resolve_index_code(q)
        if by_code:
            return render_help_body(by_code)
        n = int(q)
        entries = numbered_index_entries()
        # Legacy: single / unmatched digits as 1-based flat index
        if 1 <= n <= len(entries):
            _code, _term, _summary, key = entries[n - 1]
            return render_help_body(key)
        return fmt.join_blocks(
            fmt.err(f"No help topic numbered {n}."),
            fmt.hint("Type index for the coded list (e.g. 11, 21)."),
            gap=0,
        )
    # Legacy letter codes (1a, 2b, …) and other non-digit codes
    by_code = resolve_index_code(q)
    if by_code:
        return render_help_body(by_code)
    low = q.lower()
    if low.startswith("help "):
        q = q[5:].strip()
        by_code = resolve_index_code(q)
        if by_code:
            return render_help_body(by_code)
    elif low == "help":
        return render_numbered_index()
    return render_help_topic(q)


def print_help_query(
    query: str = "",
    *,
    console: Console | None = None,
    file: TextIO | None = None,
) -> int:
    """Print help for *query*. Always returns 0 (unknown topics still print)."""
    body = help_text_for_query(query)
    if file is not None:
        print(body, file=file)
        return 0
    con = console or Console(highlight=False)
    con.print(body)
    return 0


def run_interactive(
    *,
    console: Console | None = None,
    read_line: Callable[[], str] | None = None,
) -> int:
    """
    Tiny prompt loop: index, numbers, topics, quit.

    *read_line* is injectable for tests (defaults to ``input``).
    """
    con = console or Console(highlight=False)
    reader = read_line or (lambda: input("help› "))
    con.print(
        fmt.hint(
            f"{PRODUCT_NAME} help (line mode)  ·  "
            "index · number · topic  ·  q / quit / exit"
        )
    )
    con.print()
    con.print(help_text_for_query(""))
    while True:
        try:
            raw = reader()
        except (EOFError, KeyboardInterrupt):
            con.print()
            con.print(fmt.hint("Bye."))
            return 0
        line = (raw or "").strip()
        if not line:
            continue
        low = line.lower()
        if low in ("q", "quit", "exit", "bye"):
            con.print(fmt.hint("Bye."))
            return 0
        if low in ("0", "back", "index", "list", "topics", "help", "?"):
            con.print()
            con.print(help_text_for_query(""))
            continue
        con.print()
        con.print(help_text_for_query(line))


def run_help_tui(initial_query: str = "") -> int:
    """Launch the simple full-screen Textual help display (no world)."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical, VerticalScroll
    from textual.widgets import Footer, Header, Input, Static

    class StandaloneHelpApp(App[None]):
        """Readable help catalog: scrollable body + number/topic input."""

        TITLE = f"{PRODUCT_NAME} · Help"
        CSS = f"""
        Screen {{
            background: {HELP_TUI_BG};
        }}
        #help-shell {{
            height: 1fr;
            background: {HELP_TUI_BG};
            padding: 0 1;
        }}
        #help-chrome {{
            height: auto;
            padding: 1 1 0 1;
            color: #c8c8d0;
            border-bottom: solid {HELP_TUI_BORDER};
            background: {HELP_TUI_BG};
        }}
        #help-scroll {{
            height: 1fr;
            border: solid {HELP_TUI_BORDER};
            background: {HELP_TUI_SURFACE};
            padding: 1 2;
            margin: 1 0;
            scrollbar-background: {HELP_TUI_BG};
            scrollbar-color: {HELP_TUI_BORDER};
        }}
        #help-body {{
            height: auto;
            background: {HELP_TUI_SURFACE};
            color: #e8e8ec;
        }}
        #help-input {{
            dock: bottom;
            margin: 0 0 1 0;
            border: solid {HELP_TUI_ACCENT};
            background: {HELP_TUI_INPUT_BG};
            color: #e8e8ec;
            padding: 0 1;
        }}
        Header {{
            background: {HELP_TUI_BG};
            color: #c8c8d0;
            text-style: none;
            border-bottom: solid {HELP_TUI_BORDER};
        }}
        Footer {{
            background: {HELP_TUI_BG};
            color: #888890;
            border-top: solid {HELP_TUI_BORDER};
        }}
        """
        BINDINGS = [
            # Esc quits; q / 0 handled on submit so typing topic names still works
            Binding("escape", "quit", "Quit", show=True),
            Binding("ctrl+c", "quit", "Quit", show=False),
        ]

        def __init__(self, start_query: str = "") -> None:
            super().__init__()
            self._query = (start_query or "").strip()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Vertical(id="help-shell"):
                yield Static(
                    f"[bold {HELP_TUI_ACCENT}]help[/]  "
                    f"[dim]type number or topic · Enter  ·  0 index  ·  q / Esc quit[/dim]",
                    id="help-chrome",
                    markup=True,
                )
                with VerticalScroll(id="help-scroll"):
                    yield Static(id="help-body", markup=True)
            yield Input(
                placeholder="number · topic name · 0 index · q quit",
                id="help-input",
            )
            yield Footer()

        def on_mount(self) -> None:
            self._apply_query(self._query)
            self.query_one("#help-input", Input).focus()

        def _apply_query(self, query: str) -> None:
            body = self.query_one("#help-body", Static)
            q = (query or "").strip()
            low = q.lower()
            if low in ("q", "quit", "exit", "bye"):
                self.exit()
                return
            if low in ("0", "back", "index", "list", "topics", "help", "?"):
                q = ""
            text = help_text_for_query(q)
            body.update(text)
            self._query = q
            # Title reflects mode
            if not q:
                self.sub_title = "index"
            else:
                self.sub_title = q[:48]

        def on_input_submitted(self, event: Input.Submitted) -> None:
            line = event.value.strip()
            event.input.value = ""
            if not line:
                return
            self._apply_query(line)

    StandaloneHelpApp(start_query=initial_query).run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dos-help",
        description=(
            f"{PRODUCT_NAME} help catalog — Textual display in a second terminal "
            "(no world DB; same topics as in-game help)."
        ),
    )
    p.add_argument(
        "topic",
        nargs="*",
        help="Topic name or index number (omit for index)",
    )
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Line-mode interactive loop (not Textual)",
    )
    p.add_argument(
        "-p",
        "--print",
        action="store_true",
        dest="print_only",
        help="One-shot print to stdout (scripts / pipes; no Textual)",
    )
    p.add_argument(
        "-t",
        "--textual",
        action="store_true",
        help="Force Textual display (default on an interactive TTY)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry for console script and ``python -m dos.help_cli``."""
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    topic = " ".join(args.topic).strip()

    if args.print_only:
        return print_help_query(topic)
    if args.interactive:
        return run_interactive()
    # Textual: forced, or bare/topic launch on a real TTY
    use_tui = args.textual or sys.stdin.isatty()
    if use_tui:
        return run_help_tui(initial_query=topic)
    return print_help_query(topic)


if __name__ == "__main__":
    raise SystemExit(main())
