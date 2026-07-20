"""STUDIO Writer — shared buffer for << / <<studio (desc, lore, folio leaves).

Opens a Textual TextArea (or optional $dos_EDITOR / $EDITOR) so the
builder can move freely, edit, save (Ctrl+S) or cancel (Esc / Ctrl+Q).
Ctrl+A selects all; F2 / Alt+P toggles markup preview (no commit — avoids
VS Code stealing Ctrl+P); double-click selects a word; triple-click selects
a line. Ctrl+X is left free for cut (not cancel).

Tests inject :data:`_EDITOR_HOOK` to return a body without launching a TUI.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.widgets._text_area import Location

# (initial_text, title, studio) -> saved body or None if cancelled
_EDITOR_HOOK: Callable[[str, str, bool], str | None] | None = None


def set_editor_hook(
    hook: Callable[[str, str, bool], str | None] | None,
) -> None:
    """Install or clear a test hook that replaces the interactive editor."""
    global _EDITOR_HOOK
    _EDITOR_HOOK = hook


@dataclass
class StudioBufferResult:
    """Result of a successful buffer save (cancel is ``None`` at the screen)."""

    body: str
    # Set when the title chrome was shown (book page edit); None = not applicable
    page_title: str | None = None


@dataclass
class MultilineSession:
    """Parsed ``<<`` / ``<<studio`` opener ready to commit a body."""

    kind: str  # "desc" | "book_page" | "lore"
    studio: bool = False
    # @desc: full arg after @desc without the << marker, e.g. "" or "on quill"
    desc_rest: str = ""
    # book page meta from _parse_book_page_multiline_start
    book_meta: dict[str, Any] = field(default_factory=dict)
    # lore: add path pieces
    lore_scope: str = "place"  # place | on | ven
    lore_target: str = ""  # match / ven name when scope is on|ven
    lore_title: str = ""
    lore_when: str = ""
    initial_body: str = ""
    title: str = "Edit text"


def editor_title_for(session: MultilineSession) -> str:
    mode = "studio" if session.studio else "plain"
    if session.kind == "desc":
        rest = session.desc_rest.strip() or "here"
        return f"@desc · {rest} · {mode}"
    if session.kind == "book_page":
        meta = session.book_meta
        if meta.get("action") == "edit":
            return f"book page {meta.get('page')} · {meta.get('book_name')} · {mode}"
        return f"book page add · {meta.get('book_and_title', '')} · {mode}"
    if session.kind == "lore":
        if session.lore_scope == "on":
            return f"lore on {session.lore_target} · {mode}"
        if session.lore_scope == "ven":
            return f"lore ven {session.lore_target} · {mode}"
        return f"lore add · {mode}"
    return f"Edit · {mode}"


def run_text_editor(
    *,
    initial: str = "",
    title: str = "Edit text",
    studio: bool = False,
    page_title: str | None = None,
) -> StudioBufferResult | None:
    """
    Open the buffer editor.

    Returns :class:`StudioBufferResult` on save, or ``None`` if cancelled.
    Prefer in-process Textual TextArea; honor ``dos_EDITOR`` / ``EDITOR``
    when set and no test hook is installed.

    When *page_title* is not ``None``, the TUI shows an editable title field.
    External editors / test hooks only return body (title stays *page_title*).

    Cancel: Esc or Ctrl+Q (not Ctrl+X — that is cut).
    Select all: Ctrl+A.
    Preview: F2 or Alt+P toggles rendered markup without saving
    (Ctrl+P is reserved by VS Code Quick Open when using the integrated terminal).
    """
    if _EDITOR_HOOK is not None:
        body = _EDITOR_HOOK(initial, title, studio)
        if body is None:
            return None
        return StudioBufferResult(
            body=body,
            page_title=page_title if page_title is not None else None,
        )

    external = (os.environ.get("dos_EDITOR") or os.environ.get("EDITOR") or "").strip()
    if external:
        body = _run_external_editor(external, initial, title)
        if body is None:
            return None
        return StudioBufferResult(
            body=body,
            page_title=page_title if page_title is not None else None,
        )

    return _run_textual_editor(
        initial=initial,
        title=title,
        studio=studio,
        page_title=page_title,
    )


def _run_external_editor(cmd: str, initial: str, title: str) -> str | None:
    suffix = ".studio.txt" if "studio" in title.lower() else ".txt"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=suffix,
        delete=False,
        prefix="ws-edit-",
    ) as fh:
        path = fh.name
        fh.write(initial or "")
    try:
        # cmd may be "nano" or "code -w"
        full = f'{cmd} "{path}"' if " " in cmd and not cmd.startswith('"') else f"{cmd} {path}"
        # Prefer list form when single token
        parts = cmd.split()
        try:
            rc = subprocess.call([*parts, path])
        except OSError:
            rc = subprocess.call(full, shell=True)
        if rc != 0:
            return None
        body = Path_read(path)
        if body is None:
            return None
        return body if body.strip() else None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def Path_read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _editor_css() -> str:
    """STUDIO Writer chrome — classic DOS blue (matches main TUI)."""
    from .cli import (
        TUI_BG,
        TUI_BORDER,
        TUI_BORDER_ACCENT,
        TUI_INPUT_BG,
        TUI_MUTED,
        TUI_PANEL,
        TUI_TEXT,
        TUI_TEXT_BRIGHT,
    )

    return f"""
#editor-hint {{
    height: auto;
    color: {TUI_MUTED};
    padding: 0 1;
    background: {TUI_BG};
}}
#editor-title-row {{
    height: 3;
    width: 100%;
    padding: 0 1;
    background: {TUI_BG};
    layout: horizontal;
}}
#editor-title-label {{
    width: auto;
    height: 3;
    content-align: left middle;
    color: {TUI_MUTED};
    padding-right: 1;
}}
#editor-page-title {{
    width: 1fr;
    height: 3;
    border: solid {TUI_BORDER};
    background: {TUI_INPUT_BG};
    color: {TUI_TEXT_BRIGHT};
    padding: 0 1;
}}
#editor-gap {{
    height: 1;
    background: {TUI_BG};
}}
#editor-ruler {{
    height: auto;
    color: {TUI_BORDER_ACCENT};
    padding: 0 1;
    background: {TUI_BG};
}}
#editor-body {{
    height: 1fr;
    border: solid {TUI_BORDER_ACCENT};
    margin: 0 1 1 1;
    background: {TUI_INPUT_BG};
    color: {TUI_TEXT};
}}
#editor-preview-scroll {{
    height: 1fr;
    border: solid {TUI_BORDER};
    margin: 0 1 1 1;
    background: {TUI_INPUT_BG};
}}
#editor-preview {{
    height: auto;
    padding: 1 2;
    background: {TUI_INPUT_BG};
    color: {TUI_TEXT};
}}
"""


# Back-compat name used by ModalScreen / App CSS
EDITOR_CSS = None  # filled lazily via _get_editor_css()


def _get_editor_css() -> str:
    global EDITOR_CSS
    if not EDITOR_CSS:
        EDITOR_CSS = _editor_css()
    return EDITOR_CSS


# Shared buffer chrome brand (desc, lore, folio leaves — not folio-only)
STUDIO_WRITER_LABEL = "STUDIO Writer"
_STUDIO_WRITER_THEME_NAME = "studio_writer"


def _studio_writer_textarea_theme():
    """DOS-blue artboard + light document text (matches main TUI)."""
    from rich.style import Style
    from textual.widgets.text_area import TextAreaTheme

    from .cli import (
        TUI_BORDER_ACCENT,
        TUI_INPUT_BG,
        TUI_MUTED,
        TUI_PANEL,
        TUI_TEXT,
        TUI_TEXT_BRIGHT,
    )

    return TextAreaTheme(
        name=_STUDIO_WRITER_THEME_NAME,
        base_style=Style(color=TUI_TEXT, bgcolor=TUI_INPUT_BG),
        gutter_style=Style(color=TUI_MUTED, bgcolor=TUI_INPUT_BG),
        cursor_style=Style(color=TUI_INPUT_BG, bgcolor=TUI_TEXT_BRIGHT),
        cursor_line_style=Style(bgcolor=TUI_PANEL),
        cursor_line_gutter_style=Style(color=TUI_BORDER_ACCENT, bgcolor=TUI_PANEL),
        selection_style=Style(bgcolor="#0033cc"),
    )


def word_bounds_at(line: str, column: int) -> tuple[int, int] | None:
    """
    Inclusive-start / exclusive-end columns of the word under *column*.

    Word chars: Unicode alnum + underscore (editor-familiar). Returns None on
    whitespace / empty so the caller can leave a bare cursor.
    """
    if not line:
        return None
    col = max(0, min(int(column), len(line)))

    def is_word_char(ch: str) -> bool:
        return ch.isalnum() or ch == "_"

    if col < len(line) and is_word_char(line[col]):
        i = col
    elif col > 0 and is_word_char(line[col - 1]):
        i = col - 1
    else:
        return None
    start = i
    while start > 0 and is_word_char(line[start - 1]):
        start -= 1
    end = i + 1
    while end < len(line) and is_word_char(line[end]):
        end += 1
    return start, end


def _make_studio_writer_textarea_class():
    """
    TextArea subclass: double-click → word, triple-click → line.

    Stock Textual double-click uses widget-level select-all; we want editor
    conventions inside STUDIO Writer.
    """
    from textual import events
    from textual.widgets import TextArea
    from textual.widgets.text_area import Selection

    class StudioWriterTextArea(TextArea):
        """STUDIO Writer body: mouse multi-click selection."""

        def select_word_at(self, location: Location) -> None:
            """Select the word containing *location* (or collapse if none)."""
            row, col = self.clamp_visitable(location)
            try:
                line = self.document[row]
            except IndexError:
                self.selection = Selection.cursor((row, col))
                return
            bounds = word_bounds_at(line, col)
            if bounds is None:
                self.selection = Selection.cursor((row, col))
                return
            start_col, end_col = bounds
            self.selection = Selection((row, start_col), (row, end_col))
            self.record_cursor_width()

        async def _on_click(self, event: events.Click) -> None:
            # chain 2 = double, 3 = triple (Textual Click.chain)
            if event.chain >= 2 and event.widget is self:
                event.stop()
                target = self.get_target_document_location(event)
                if event.chain == 2:
                    self.select_word_at(target)
                else:
                    # triple (or more): whole logical line
                    self.select_line(target[0])
                self.focus()
                return
            await super()._on_click(event)

    return StudioWriterTextArea


def _make_editor_textarea(initial: str):
    """TextArea for STUDIO Writer: light text on black, prefilled body."""
    StudioWriterTextArea = _make_studio_writer_textarea_class()

    ta = StudioWriterTextArea(
        text=initial or "",
        id="editor-body",
        # vscode_dark until mount registers studio_writer (instance method)
        theme="vscode_dark",
        show_line_numbers=True,
        soft_wrap=True,
        tab_behavior="indent",
    )
    return ta


def _mount_editor_body(screen_or_app, initial: str) -> None:
    """Apply STUDIO Writer theme, re-seed text if needed, focus body."""
    from textual.widgets import TextArea

    ta = screen_or_app.query_one("#editor-body", TextArea)
    theme = _studio_writer_textarea_theme()
    ta.register_theme(theme)
    ta.theme = _STUDIO_WRITER_THEME_NAME
    want = initial or ""
    # Guard: construct-time text must survive into the open buffer
    if (ta.text or "") != want:
        ta.load_text(want)
    ta.focus()


def _editor_hint_markup(
    title: str,
    *,
    studio: bool,
    with_page_title: bool = False,
    preview: bool = False,
) -> str:
    """Brand tag + save/cancel tips for the buffer header."""
    from .measure import CONTENT_MEASURE

    mode = "Studio Text" if studio else "plain"
    view = "[bold green]PREVIEW[/]" if preview else "[bold]EDIT[/]"
    measure_note = f"  ·  measure {CONTENT_MEASURE}" if studio else ""
    title_note = "  ·  page title above" if with_page_title else ""
    return (
        f"[bold #d4a574]{STUDIO_WRITER_LABEL}[/]  ·  "
        f"[bold]{title}[/bold]  ·  {mode}  ·  {view}{measure_note}{title_note}  ·  "
        f"F2/Alt+P preview  ·  Ctrl+A all  ·  Ctrl+S save  ·  Esc cancel"
    )


def _preview_markup(source: str, *, studio: bool) -> str:
    """Render buffer body for the preview pane (does not write storage)."""
    from .format import safe
    from .studio_text import render_studio_text

    text = source if source is not None else ""
    if not text.strip():
        return "[dim](empty buffer)[/dim]"
    if studio:
        return render_studio_text(text)
    return safe(text)


def _editor_ruler_markup() -> str:
    """Bright content-measure ruler (no dim) aligned to line-number gutter."""
    from .measure import CONTENT_MEASURE, measure_ruler

    gutter = "    "  # ~4 cols for TextArea line numbers
    return f"{gutter}{measure_ruler(CONTENT_MEASURE)}"


def make_studio_buffer_screen(
    *,
    initial: str = "",
    title: str = "Edit text",
    studio: bool = False,
    page_title: str | None = None,
):
    """
    Textual ModalScreen[StudioBufferResult|None] for nesting inside the main TUI.

    When *page_title* is not ``None``, show an editable page-title field above
    the body (book page edit). Dismisses ``StudioBufferResult`` on save.
    """
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.screen import ModalScreen
    from textual.widgets import Footer, Input, Static, TextArea

    show_title = page_title is not None
    _css = _get_editor_css()

    class StudioBufferScreen(ModalScreen[StudioBufferResult | None]):
        CSS = _css
        BINDINGS = [
            # F2 / Alt+P: Ctrl+P is stolen by VS Code Quick Open in the integrated terminal
            Binding("f2", "toggle_preview", "Preview", show=True, priority=True),
            Binding("alt+p", "toggle_preview", "Preview", show=False, priority=True),
            Binding("ctrl+a", "select_all", "Select all", show=True, priority=True),
            Binding("ctrl+s", "save", "Save", show=True, priority=True),
            Binding("ctrl+q", "cancel", "Cancel", show=True, priority=True),
            Binding("escape", "cancel", "Cancel", show=True, priority=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._preview_mode = False

        def compose(self) -> ComposeResult:
            from textual.containers import VerticalScroll

            yield Static(
                _editor_hint_markup(
                    title, studio=studio, with_page_title=show_title
                ),
                id="editor-hint",
                markup=True,
            )
            if show_title:
                with Horizontal(id="editor-title-row"):
                    yield Static(
                        "[dim]Title[/dim]",
                        id="editor-title-label",
                        markup=True,
                    )
                    yield Input(
                        value=page_title or "",
                        placeholder="page title",
                        id="editor-page-title",
                    )
            if studio:
                yield Static("", id="editor-gap")
                yield Static(
                    _editor_ruler_markup(),
                    id="editor-ruler",
                    markup=True,
                )
            yield _make_editor_textarea(initial or "")
            with VerticalScroll(id="editor-preview-scroll"):
                yield Static("", id="editor-preview", markup=True)
            yield Footer()

        def on_mount(self) -> None:
            _mount_editor_body(self, initial or "")
            try:
                self.query_one("#editor-preview-scroll").display = False
            except Exception:  # noqa: BLE001
                pass

        def _draft_text(self) -> str:
            ta = self.query_one("#editor-body", TextArea)
            return ta.text if ta is not None else ""

        def _refresh_hint(self) -> None:
            try:
                hint = self.query_one("#editor-hint", Static)
                hint.update(
                    _editor_hint_markup(
                        title,
                        studio=studio,
                        with_page_title=show_title,
                        preview=self._preview_mode,
                    )
                )
            except Exception:  # noqa: BLE001
                pass

        def action_toggle_preview(self) -> None:
            ta = self.query_one("#editor-body", TextArea)
            scroll = self.query_one("#editor-preview-scroll")
            prev = self.query_one("#editor-preview", Static)
            if not self._preview_mode:
                src = ta.text or ""
                prev.update(_preview_markup(src, studio=studio))
                ta.display = False
                scroll.display = True
                self._preview_mode = True
                try:
                    ruler = self.query_one("#editor-ruler")
                    ruler.display = False
                except Exception:  # noqa: BLE001
                    pass
                self.notify("Preview · F2 / Alt+P back to edit", timeout=2)
            else:
                scroll.display = False
                ta.display = True
                self._preview_mode = False
                try:
                    ruler = self.query_one("#editor-ruler")
                    ruler.display = True
                except Exception:  # noqa: BLE001
                    pass
                ta.focus()
                self.notify("Edit", timeout=1)
            self._refresh_hint()

        def action_select_all(self) -> None:
            if self._preview_mode:
                return
            ta = self.query_one("#editor-body", TextArea)
            ta.focus()
            ta.select_all()

        def action_save(self) -> None:
            text = self._draft_text()
            if not (text or "").strip():
                self.notify("Empty buffer — add text or cancel.", severity="warning")
                return
            pt: str | None = None
            if show_title:
                pt = self.query_one("#editor-page-title", Input).value
                pt = (pt or "").strip()
            self.dismiss(StudioBufferResult(body=text, page_title=pt))

        def action_cancel(self) -> None:
            if self._preview_mode:
                # first Esc from preview returns to edit (safer than discard)
                self.action_toggle_preview()
                return
            self.dismiss(None)

    return StudioBufferScreen()


def _run_textual_editor(
    *,
    initial: str,
    title: str,
    studio: bool,
    page_title: str | None = None,
) -> StudioBufferResult | None:
    """Blocking Textual app; F2/Alt+P preview, Ctrl+A, Ctrl+S save, Esc / Ctrl+Q cancel."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, VerticalScroll
    from textual.widgets import Footer, Header, Input, Static, TextArea

    result: dict[str, StudioBufferResult | None] = {"out": None}
    show_title = page_title is not None
    from .cli import TUI_BG

    _app_css = f"Screen {{ background: {TUI_BG}; }}\n" + _get_editor_css()

    class StudioBufferApp(App[None]):
        CSS = _app_css
        BINDINGS = [
            Binding("f2", "toggle_preview", "Preview", show=True, priority=True),
            Binding("alt+p", "toggle_preview", "Preview", show=False, priority=True),
            Binding("ctrl+a", "select_all", "Select all", show=True, priority=True),
            Binding("ctrl+s", "save", "Save", show=True, priority=True),
            Binding("ctrl+q", "cancel", "Cancel", show=True, priority=True),
            Binding("escape", "cancel", "Cancel", show=True, priority=True),
        ]
        def __init__(self) -> None:
            super().__init__()
            self._preview_mode = False

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            yield Static(
                _editor_hint_markup(
                    title, studio=studio, with_page_title=show_title
                ),
                id="editor-hint",
                markup=True,
            )
            if show_title:
                with Horizontal(id="editor-title-row"):
                    yield Static(
                        "[dim]Title[/dim]",
                        id="editor-title-label",
                        markup=True,
                    )
                    yield Input(
                        value=page_title or "",
                        placeholder="page title",
                        id="editor-page-title",
                    )
            if studio:
                yield Static("", id="editor-gap")
                yield Static(
                    _editor_ruler_markup(),
                    id="editor-ruler",
                    markup=True,
                )
            yield _make_editor_textarea(initial or "")
            with VerticalScroll(id="editor-preview-scroll"):
                yield Static("", id="editor-preview", markup=True)
            yield Footer()

        def on_mount(self) -> None:
            self.title = title
            _mount_editor_body(self, initial or "")
            try:
                self.query_one("#editor-preview-scroll").display = False
            except Exception:  # noqa: BLE001
                pass

        def _draft_text(self) -> str:
            ta = self.query_one("#editor-body", TextArea)
            return ta.text if ta is not None else ""

        def _refresh_hint(self) -> None:
            try:
                hint = self.query_one("#editor-hint", Static)
                hint.update(
                    _editor_hint_markup(
                        title,
                        studio=studio,
                        with_page_title=show_title,
                        preview=self._preview_mode,
                    )
                )
            except Exception:  # noqa: BLE001
                pass

        def action_toggle_preview(self) -> None:
            ta = self.query_one("#editor-body", TextArea)
            scroll = self.query_one("#editor-preview-scroll")
            prev = self.query_one("#editor-preview", Static)
            if not self._preview_mode:
                src = ta.text or ""
                prev.update(_preview_markup(src, studio=studio))
                ta.display = False
                scroll.display = True
                self._preview_mode = True
                try:
                    ruler = self.query_one("#editor-ruler")
                    ruler.display = False
                except Exception:  # noqa: BLE001
                    pass
                self.notify("Preview · F2 / Alt+P back to edit", timeout=2)
            else:
                scroll.display = False
                ta.display = True
                self._preview_mode = False
                try:
                    ruler = self.query_one("#editor-ruler")
                    ruler.display = True
                except Exception:  # noqa: BLE001
                    pass
                ta.focus()
                self.notify("Edit", timeout=1)
            self._refresh_hint()

        def action_select_all(self) -> None:
            if self._preview_mode:
                return
            ta = self.query_one("#editor-body", TextArea)
            ta.focus()
            ta.select_all()

        def action_save(self) -> None:
            text = self._draft_text()
            if not (text or "").strip():
                self.notify("Empty buffer — add text or cancel.", severity="warning")
                return
            pt: str | None = None
            if show_title:
                pt = self.query_one("#editor-page-title", Input).value
                pt = (pt or "").strip()
            result["out"] = StudioBufferResult(body=text, page_title=pt)
            self.exit()

        def action_cancel(self) -> None:
            if self._preview_mode:
                self.action_toggle_preview()
                return
            result["out"] = None
            self.exit()

    StudioBufferApp().run()
    return result["out"]
