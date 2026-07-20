"""TUI book reader: soft full-width modal over the world log.

Fixed-height frame so short leaves still open a full reader. Layout:

  left:  {book_name} · {code}
  right: {status} · leaf n/m
  body:  scrollable leaf content (title + lines) independent of the frame
  foot:  < / > browse · + add leaf · e edit · esc close

Leaves are the formal unit of book material. Studio stays **page-singular**:
``e`` edits the current leaf (title + body). ``+`` inserts a new leaf
*after* the current one and opens the editor (harder to hit than ``a``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .world import World

# Minimal body so a new leaf can open studio without an empty-buffer trap.
# User replaces this on first save (or keeps a blank line after strip fails —
# a single space is stripped, so use a visible seed).
_NEW_LEAF_BODY_SEED = "…"


def make_book_reader_screen(
    world: World,
    book_instance_id: str,
    *,
    page_index: int = 0,
):
    """
    ModalScreen that reads *book_instance_id*.

    Dismisses with ``None``. Owns its leaf index; parent may track open book
    only for mutual exclusion with help.
    """
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Static

    from .book import (
        PAGE_VIEW_WIDTH,
        format_page_body,
        format_status_markup,
        page_index_after_nav,
    )
    from .ids import display_name

    # Fixed body column = content measure; CSS width must match for equal L/R pad
    _BODY_W = max(40, int(PAGE_VIEW_WIDTH))

    class BookReaderScreen(ModalScreen[None]):
        """Soft-dim fixed-height book reader over the studio log."""

        IS_BOOK_READER = True

        CSS = f"""
        BookReaderScreen {{
            align: center middle;
            background: rgba(10, 10, 12, 0.52);
        }}
        #book-reader {{
            width: 90%;
            max-width: 86;
            /* Consistent frame height — short leaves don’t shrink the modal */
            height: 80%;
            min-height: 22;
            max-height: 92%;
            background: #0c0c10;
            border: solid #5ec8d8;
            padding: 0 1;
            color: #e8e8ec;
            layout: vertical;
        }}
        #book-reader-header {{
            height: 3;
            width: 100%;
            padding: 0 1;
            border-bottom: solid #3d3d48;
            background: #0c0c10;
            layout: horizontal;
        }}
        #book-reader-left {{
            width: 1fr;
            height: 3;
            content-align: left middle;
            color: #e8e8ec;
        }}
        #book-reader-right {{
            width: auto;
            min-width: 22;
            height: 3;
            content-align: right middle;
            color: #c8c8d0;
            padding-left: 1;
        }}
        #book-reader-scroll {{
            height: 1fr;
            width: 100%;
            background: #000000;
            /* Equal inset L/R; body column is fixed measure and centered */
            padding: 1 1;
            align: center top;
            scrollbar-background: #0a0a0c;
            scrollbar-color: #3d3d48;
            scrollbar-size-vertical: 1;
        }}
        #book-reader-body {{
            height: auto;
            width: {_BODY_W};
            max-width: 100%;
            background: #000000;
            color: #e8e8ec;
            text-align: left;
        }}
        #book-reader-foot {{
            height: 3;
            width: 100%;
            padding: 0 1;
            border-top: solid #3d3d48;
            content-align: center middle;
            color: #888890;
            background: #0c0c10;
        }}
        """

        # Screen can take focus so keybindings keep working after nested studio
        can_focus = True

        BINDINGS = [
            Binding("left", "prev", "Prev leaf", show=True, priority=True),
            Binding("right", "next", "Next leaf", show=True, priority=True),
            Binding("h", "prev", "Prev", show=False, priority=True),
            Binding("H", "prev", "Prev", show=False, priority=True),
            Binding("l", "next", "Next", show=False, priority=True),
            Binding("L", "next", "Next", show=False, priority=True),
            Binding("escape", "close", "Close", show=True, priority=True),
            Binding("q", "close", "Close", show=False, priority=True),
            Binding("Q", "close", "Close", show=False, priority=True),
            # Both cases: caps lock turns "e" into "E" (not the same binding)
            Binding("e", "edit_page", "Edit leaf", show=True, priority=True),
            Binding("E", "edit_page", "Edit leaf", show=False, priority=True),
            # plus — deliberate add (not bare "a" / unshifted =)
            Binding("plus", "add_leaf", "Add leaf", show=True, priority=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._book_id = book_instance_id
            self._page_index = max(0, int(page_index))
            # Prevent stacked studio screens / lost focus after many open/close
            self._studio_open = False

        def compose(self) -> ComposeResult:
            with Vertical(id="book-reader"):
                with Horizontal(id="book-reader-header"):
                    yield Static("", id="book-reader-left", markup=True)
                    yield Static("", id="book-reader-right", markup=True)
                with VerticalScroll(id="book-reader-scroll"):
                    yield Static("", id="book-reader-body", markup=True)
                yield Static(
                    "[dim]< / > browse  ·  + add leaf  ·  e edit  ·  esc close[/dim]",
                    id="book-reader-foot",
                    markup=True,
                )

        def on_mount(self) -> None:
            self._refresh_view()
            self._refocus_reader()

        def _refocus_reader(self) -> None:
            """Restore key focus after studio dismiss (nested modal focus bug)."""

            def _go() -> None:
                if not self.is_attached:
                    return
                try:
                    scroll = self.query_one(
                        "#book-reader-scroll", VerticalScroll
                    )
                    scroll.can_focus = True
                    self.set_focus(scroll)
                except Exception:  # noqa: BLE001
                    try:
                        self.focus()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    self.refresh_bindings()
                except Exception:  # noqa: BLE001
                    pass

            try:
                self.call_after_refresh(_go)
            except Exception:  # noqa: BLE001
                _go()

        def _pages(self) -> list[Any]:
            return list(world.list_book_pages(self._book_id))

        def _refresh_view(self) -> None:
            left = self.query_one("#book-reader-left", Static)
            right = self.query_one("#book-reader-right", Static)
            body = self.query_one("#book-reader-body", Static)

            book = world.get_instance(self._book_id)
            if book is None:
                left.update("[dim]Book missing[/dim]")
                right.update("")
                body.update("[dim]Book missing.[/dim]")
                return

            name = display_name(book.name)
            safe_name = (
                str(name).replace("\\", "\\\\").replace("[", "\\[")
            )
            try:
                code = world.short_ref_of(self._book_id)
            except Exception:  # noqa: BLE001
                code = book.ven_code or "—"
            left.update(
                f"[bold]{safe_name}[/bold]  [dim]·[/dim]  "
                f"[dim]{code}[/dim]"
            )

            pages = self._pages()
            status = world.book_status(self._book_id)
            count = len(pages)
            self._page_index = page_index_after_nav(self._page_index, 0, count)
            n = self._page_index + 1 if count else 0
            status_mk = format_status_markup(status)
            right.update(f"{status_mk}  [dim]·[/dim]  leaf {n}/{count}")

            if count == 0:
                body.update(
                    format_page_body(
                        page_index=0,
                        page_count=0,
                        title="",
                        body="",
                    )
                )
            else:
                page = pages[self._page_index]
                body.update(
                    format_page_body(
                        page_index=self._page_index,
                        page_count=count,
                        title=page["title"] or "",
                        body=page["body"] or "",
                    )
                )
            try:
                scroll = self.query_one("#book-reader-scroll", VerticalScroll)
                scroll.scroll_home(animate=False)
            except Exception:  # noqa: BLE001
                pass

        def action_prev(self) -> None:
            pages = self._pages()
            self._page_index = page_index_after_nav(
                self._page_index, -1, len(pages)
            )
            self._refresh_view()

        def action_next(self) -> None:
            pages = self._pages()
            self._page_index = page_index_after_nav(
                self._page_index, 1, len(pages)
            )
            self._refresh_view()

        def action_close(self) -> None:
            self.dismiss(None)

        def action_add_leaf(self) -> None:
            """Insert a new leaf after the current one; open studio to write it."""
            from .commands import _push_book_page_delete_undo
            from .studio_text import prepare_stored_text

            book = world.get_instance(self._book_id)
            if book is None:
                self.notify("Book missing.", severity="error")
                return

            pages = self._pages()
            count = len(pages)
            if count == 0:
                insert_at = 1
                new_index = 0
            else:
                self._page_index = page_index_after_nav(
                    self._page_index, 0, count
                )
                cur_pos = int(pages[self._page_index]["position"])
                insert_at = cur_pos + 1  # after current
                new_index = self._page_index + 1

            seed_body = prepare_stored_text(_NEW_LEAF_BODY_SEED, studio=True)
            try:
                pid = world.add_book_page(
                    self._book_id,
                    "",  # title filled in studio
                    seed_body,
                    position=insert_at,
                )
            except Exception as e:  # noqa: BLE001
                self.notify(f"Could not add leaf: {e}", severity="error")
                return

            _push_book_page_delete_undo(
                world,
                self._book_id,
                pid,
                f"add leaf {display_name(book.name)}",
            )
            self._page_index = new_index
            self._refresh_view()
            self.notify("Leaf added.", severity="information")
            # Drop into singular studio on the new leaf
            self.action_edit_page()

        def action_edit_page(self) -> None:
            """Open studio buffer for the current leaf; save title + body."""
            from .studio_text import strip_studio_header, prepare_stored_text
            from .text_editor import StudioBufferResult, make_studio_buffer_screen
            from .commands import (
                _push_book_page_title_body_undo,
            )

            # Nested studio already open (or dismiss in flight) — ignore e spam
            if self._studio_open:
                return

            book = world.get_instance(self._book_id)
            if book is None:
                self.notify("Book missing.", severity="error")
                return
            pages = self._pages()
            if not pages:
                self.notify(
                    "Empty book — press + to add a leaf.",
                    severity="warning",
                )
                return
            self._page_index = page_index_after_nav(
                self._page_index, 0, len(pages)
            )
            page = pages[self._page_index]
            pos = int(page["position"])
            page_id = page["id"]
            prior_title = page["title"] or ""
            prior_body = page["body"] or ""
            initial = strip_studio_header(prior_body)
            # Drop seed ellipsis for a clean first write
            if initial.strip() == _NEW_LEAF_BODY_SEED:
                initial = ""
            title = (
                f"leaf {pos} · {display_name(book.name)} · studio"
            )
            screen = make_studio_buffer_screen(
                initial=initial,
                title=title,
                studio=True,
                page_title=prior_title,
            )

            self._studio_open = True

            def _on_edit_done(result: StudioBufferResult | None) -> None:
                try:
                    if result is None:
                        self.notify(
                            "Edit cancelled.", severity="information"
                        )
                        return
                    if not (result.body or "").strip():
                        self.notify(
                            "Empty buffer — not saved.", severity="warning"
                        )
                        return
                    new_title = (
                        (result.page_title or "").strip()
                        if result.page_title is not None
                        else prior_title
                    )
                    new_body = prepare_stored_text(result.body, studio=True)
                    try:
                        world.set_book_page_title(
                            self._book_id, pos, new_title
                        )
                        world.set_book_page_body(
                            self._book_id, pos, new_body
                        )
                    except Exception as e:  # noqa: BLE001
                        self.notify(f"Save failed: {e}", severity="error")
                        return
                    if new_title != prior_title or new_body != prior_body:
                        _push_book_page_title_body_undo(
                            world,
                            page_id,
                            prior_title,
                            prior_body,
                            f"leaf edit {display_name(book.name)} {pos}",
                        )
                    self.notify("Leaf saved.", severity="information")
                    self._refresh_view()
                finally:
                    self._studio_open = False
                    # Critical: nested modal leaves reader without focus → e dies
                    self._refocus_reader()

            try:
                # push_screen lives on App (not Screen) in our Textual version
                self.app.push_screen(screen, _on_edit_done)
            except Exception:  # noqa: BLE001
                self._studio_open = False
                raise

    return BookReaderScreen()
