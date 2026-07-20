"""TUI wiki dossier: soft full-width modal (same frame language as the folio reader)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World


def make_wiki_reader_screen(
    world: World,
    label: str,
    *,
    deep: bool = False,
):
    """
    ModalScreen showing a wiki dossier for *label*.

    Dismisses with ``None``. Header mirrors the book reader; body is the dossier
    (no edit / leaf chrome — wiki is read-only here).
    """
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Static

    from . import format as fmt
    from .ids import display_name
    from .wiki import format_wiki_dossier, resolve_wiki_target
    from .world import format_kind_label

    class WikiReaderScreen(ModalScreen[None]):
        """Soft-dim fixed-height wiki dossier over the studio log."""

        IS_WIKI_READER = True
        # Share mutual-exclusion bit with book reader (either soft reader)
        IS_BOOK_READER = True

        CSS = """
        WikiReaderScreen {
            align: center middle;
            background: rgba(10, 10, 12, 0.52);
        }
        #wiki-reader {
            width: 90%;
            max-width: 86;
            height: 80%;
            min-height: 22;
            max-height: 92%;
            background: #0c0c10;
            border: solid #5ec8d8;
            padding: 0 1;
            color: #e8e8ec;
            layout: vertical;
        }
        #wiki-reader-header {
            height: 3;
            width: 100%;
            padding: 0 1;
            border-bottom: solid #3d3d48;
            background: #0c0c10;
            layout: horizontal;
        }
        #wiki-reader-left {
            width: 1fr;
            height: 3;
            content-align: left middle;
            color: #e8e8ec;
        }
        #wiki-reader-right {
            width: auto;
            min-width: 18;
            height: 3;
            content-align: right middle;
            color: #c8c8d0;
            padding-left: 1;
        }
        #wiki-reader-scroll {
            height: 1fr;
            width: 100%;
            background: #000000;
            padding: 1 2;
            scrollbar-background: #0a0a0c;
            scrollbar-color: #3d3d48;
            scrollbar-size-vertical: 1;
        }
        #wiki-reader-body {
            height: auto;
            width: 100%;
            background: #000000;
            color: #e8e8ec;
        }
        #wiki-reader-foot {
            height: 3;
            width: 100%;
            padding: 0 1;
            border-top: solid #3d3d48;
            content-align: center middle;
            color: #888890;
            background: #0c0c10;
        }
        """

        BINDINGS = [
            Binding("escape", "close", "Close", show=True, priority=True),
            Binding("q", "close", "Close", show=False, priority=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._label = (label or "").strip()
            self._deep = bool(deep)

        def compose(self) -> ComposeResult:
            with Vertical(id="wiki-reader"):
                with Horizontal(id="wiki-reader-header"):
                    yield Static("", id="wiki-reader-left", markup=True)
                    yield Static("", id="wiki-reader-right", markup=True)
                with VerticalScroll(id="wiki-reader-scroll"):
                    yield Static("", id="wiki-reader-body", markup=True)
                yield Static(
                    "[dim]esc close  ·  wiki is read-only here[/dim]",
                    id="wiki-reader-foot",
                    markup=True,
                )

        def on_mount(self) -> None:
            self._refresh_view()
            try:
                self.query_one("#wiki-reader-scroll", VerticalScroll).focus()
            except Exception:  # noqa: BLE001
                pass

        def _refresh_view(self) -> None:
            left = self.query_one("#wiki-reader-left", Static)
            right = self.query_one("#wiki-reader-right", Static)
            body = self.query_one("#wiki-reader-body", Static)

            target = resolve_wiki_target(world, self._label)
            if target.status in ("missing", "ambiguous"):
                left.update("[bold]Wiki[/bold]")
                right.update("[dim]—[/dim]")
                body.update(format_wiki_dossier(world, target, deep=self._deep))
                return

            ven = target.ven
            inst = target.instance
            if ven is None and inst is not None:
                ven = world.get_ven(inst.ven_id)
            if ven is None:
                left.update("[bold]Wiki[/bold]")
                right.update("")
                body.update(fmt.err("Missing VEN for wiki target."))
                return

            title_name = display_name(inst.name) if inst else display_name(ven.name)
            safe_name = str(title_name).replace("\\", "\\\\").replace("[", "\\[")
            code = (ven.code or ven.slug or "—").strip()
            left.update(
                f"[bold]Wiki · {safe_name}[/bold]  [dim]·[/dim]  "
                f"[dim]{fmt.safe(code)}[/dim]"
            )
            kind_lab = format_kind_label(ven.kind, ven.subtype)
            scope = "instance" if inst is not None else "prime"
            deep_bit = "  ·  deep" if self._deep else ""
            right.update(
                f"[dim]{fmt.safe(kind_lab)}  ·  {scope}{deep_bit}[/dim]"
            )
            body.update(
                format_wiki_dossier(
                    world,
                    target,
                    deep=self._deep,
                    include_title=False,
                )
            )
            try:
                scroll = self.query_one("#wiki-reader-scroll", VerticalScroll)
                scroll.scroll_home(animate=False)
            except Exception:  # noqa: BLE001
                pass

        def action_close(self) -> None:
            self.dismiss(None)

    return WikiReaderScreen()
