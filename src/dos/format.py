"""Calm, Grok-Build-adjacent terminal presentation helpers.

Shared chrome for room views and lists: clear hierarchy, dim secondary text,
safe escaping so user/world strings cannot inject Rich markup.
"""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape as rich_escape

from . import PRODUCT_NAME
from .ids import display_name
from .measure import CONTENT_MEASURE, turn_rule_ascii

# Soft accent used sparingly (prompt / section rules), not on every line.
ACCENT = "bright_cyan"
MUTED = "dim"
TITLE = "bold"
OK = "green"
ERR = "red"
LABEL_WIDTH = 10

# Distinct Rich color per VEN kind (and soft colors for link types).
KIND_COLORS: dict[str, str] = {
    "person": "yellow",
    "place": "bright_white",
    "bin": "bright_cyan",
    "container": "bright_cyan",  # legacy kind color
    "thing": "bright_yellow",
    "folio": "bright_yellow",
    "symbol": "white",
    "sense": "magenta",
    "realm": "cyan",
    "timeline": "bright_green",
    # legacy aliases (same colors as folded roots)
    "object": "bright_yellow",
    "book": "bright_yellow",
    "material": "gold1",
    "concept": "white",
    "feeling": "magenta",
    "goal": "bright_magenta",
    "desire": "magenta",
    "purpose": "bright_magenta",
    "event": "bright_yellow",
    "archetype": "yellow",
    "other": "white",
}

LINK_TYPE_COLORS: dict[str, str] = {
    "spatial": "bright_blue",
    "dimensional": "bright_cyan",  # was magenta; less purple noise near locations
    "temporal": "bright_green",
    "narrative": "cyan",
    "conditional": "yellow",
}

# Turn boundary matches the canonical content measure (ASCII, portable).
TURN_RULE_WIDTH = CONTENT_MEASURE


def turn_separator() -> str:
    """
    Single-line divider between interactive command turns.

    ASCII dashes at :data:`CONTENT_MEASURE` so rules match book/studio artboard
    width and copy-paste cleanly.
    """
    return f"[dim]{turn_rule_ascii(TURN_RULE_WIDTH)}[/dim]"


def safe(text: object) -> str:
    """Escape arbitrary world/user text for Rich markup strings."""
    if text is None:
        return ""
    return rich_escape(str(text))


def plain(text: object) -> str:
    """Strip Rich markup for assertions / plain capture checks."""
    console = Console(force_terminal=False, no_color=True, width=120)
    with console.capture() as cap:
        console.print(str(text), markup=True, highlight=False, end="")
    return cap.get()


def show_name(name: object) -> str:
    """Escaped player-facing entity name (plain readable, not cute storage form)."""
    return safe(display_name(str(name) if name is not None else ""))


def named_ref(name: object, ref: object) -> str:
    """
    Player-facing ``Name #CODE`` with a space before the hash.

    Use in success lines, titles, and lore headings. Prefer this over gluing
    ``Name#CODE``. Command tokens that must parse as ``name#CODE`` stay glued
    at the call site (e.g. book open examples).

    Plain text (not Rich-escaped) — pass through :func:`ok` / :func:`err` or
    escape with :func:`safe` when embedding in markup.
    """
    n = display_name(str(name) if name is not None else "")
    r = str(ref or "").strip().lstrip("#")
    if not r:
        return n
    if not n:
        return f"#{r}"
    return f"{n} #{r}"


def kind_color(kind: str) -> str:
    """Rich color name for a VEN kind (fallback white)."""
    return KIND_COLORS.get((kind or "").lower().strip(), "white")


def kind_label(kind: str) -> str:
    """Dim secondary kind reference (not the colored focus)."""
    k = (kind or "").strip() or "other"
    return f"[dim]{safe(k)}[/dim]"


def kind_markup(kind: str) -> str:
    """Deprecated alias: kind words stay dim; prefer colored_name for entities."""
    return kind_label(kind)


def colored_name(name: object, kind: str | None = None) -> str:
    """Player-facing name, colored by VEN kind when kind is given."""
    text = show_name(name)
    if not kind:
        return text
    color = kind_color(kind)
    return f"[{color}]{text}[/{color}]"


def link_type_markup(link_type: str) -> str:
    """Colored link-type word inside parentheses on exit lines."""
    t = (link_type or "").strip() or "spatial"
    color = LINK_TYPE_COLORS.get(t.lower(), MUTED)
    return f"[{color}]{safe(t)}[/{color}]"


def title_line(name: str, kind: str | None = None) -> str:
    """Bold place/entity title; optional kind tints the name."""
    if kind:
        color = kind_color(kind)
        return f"[{TITLE} {color}]{show_name(name)}[/{TITLE} {color}]"
    return f"[{TITLE} {ACCENT}]{show_name(name)}[/{TITLE} {ACCENT}]"


def rule(label: str = "") -> str:
    """Thin section divider; optional label on the left."""
    if label:
        return f"[dim]── {safe(label)} ────────────────────────────[/dim]"
    return "[dim]──────────────────────────────────────[/dim]"


def section(label: str) -> str:
    """Section header: short uppercase-feeling label, restrained."""
    return f"[bold]{safe(label)}[/bold]"


def meta_row(
    label: str,
    value: str,
    secondary: str | None = None,
    *,
    name: bool = False,
    kind: str | None = None,
) -> str:
    """Aligned key/value for whereami-style panels.

    name=True → run display_name on value first.
    kind=... → color the **value** (entity name) by kind; field label stays dim.
    """
    lab = safe(label).ljust(LABEL_WIDTH)
    if kind:
        if name:
            val = colored_name(value, kind)
        else:
            # Already human-readable (e.g. status Situation fields)
            val = f"[{kind_color(kind)}]{safe(value)}[/{kind_color(kind)}]"
    elif name:
        val = show_name(value)
    else:
        val = safe(value)
    line = f"[dim]{lab}[/dim] {val}"
    if secondary:
        line += f"  [dim]{safe(secondary)}[/dim]"
    return line


def bullet(primary: str, secondary: str | None = None, *, kind: str | None = None) -> str:
    """
    List row. ``kind=`` colors the entity name.

    When *secondary* is omitted, a dim kind word is appended (inv-style).
    When *secondary* is set, only that meta is shown (no second kind word) —
    so callers can pass ``kind/subtype · code`` without ``place place``.
    """
    name = colored_name(primary, kind) if kind else show_name(primary)
    if secondary:
        return f"  [dim]·[/dim] {name}  [dim]{safe(secondary)}[/dim]"
    if kind:
        return f"  [dim]·[/dim] {name}  {kind_label(kind)}"
    return f"  [dim]·[/dim] {name}"


def pad_visible(text: str, width: int, *, align: str = "left") -> str:
    """Pad plain text to *width* (for table columns; no Rich markup in *text*)."""
    s = text if text is not None else ""
    if width < 1:
        return s
    if len(s) >= width:
        return s
    pad = width - len(s)
    if align == "right":
        return (" " * pad) + s
    return s + (" " * pad)


def colored_padded_name(name: str, kind: str | None, width: int) -> str:
    """Kind-colored name, space-padded to *width* using the plain display length."""
    shown = show_name(name)
    pad = max(0, width - len(shown))
    if kind:
        return colored_name(shown, kind) + (" " * pad)
    return show_name(shown) + (" " * pad)


def inner_life_row(
    instance_name: str,
    ven_name: str,
    kind: str,
    subtype: str | None = None,
) -> str:
    """
    Person Inner life list line: instance · VEN · type · subtype.

    Field order:
      0. Instance name (this copy; includes name override when set) — colored by kind
      1. Prime VEN name (dim)
      2. VEN kind/type (once)
      3. Subtype when set; otherwise ``-`` (never a second copy of the kind)
    """
    inst = colored_name(instance_name, kind)
    ven = f"[dim]{show_name(ven_name)}[/dim]"
    type_part = kind_label(kind)
    sub = (subtype or "").strip() or "-"
    return f"  [dim]·[/dim] {inst}  {ven}  {type_part}  [dim]{safe(sub)}[/dim]"


def stacked_item(title: str, detail: str, *, kind: str | None = None) -> str:
    """Two-line list entry for long names (avoids broken fixed-width tables)."""
    if kind:
        head = f"  [dim]·[/dim] {colored_name(title, kind)}"
    else:
        head = f"  [dim]·[/dim] {show_name(title)}"
    return f"{head}\n      [dim]{safe(detail)}[/dim]"


def exit_line(label: str, link_type: str, dest: str, dest_kind: str = "place") -> str:
    return (
        f"  [dim]·[/dim] {safe(label)}  "
        f"({link_type_markup(link_type)})  →  {colored_name(dest, dest_kind)}"
    )


def prose(text: str) -> str:
    """
    Render world/user longform text for look / examine / lore.

    Plain bodies are fully escaped. Bodies stored with ``.format: studio``
    (or written via studio opt-in commands) use Studio Text whitelist markup.
    """
    from .studio_text import render_body

    return render_body(text)


def hint(text: str) -> str:
    """Secondary/muted line; always escapes so world/user text cannot inject markup."""
    return f"[dim]{safe(text)}[/dim]"


def ok(msg: str) -> str:
    return f"[{OK}]{safe(msg)}[/{OK}]"


def err(msg: str) -> str:
    return f"[{ERR}]{safe(msg)}[/{ERR}]"


def join_blocks(*blocks: str | None, gap: int = 1) -> str:
    """Join non-empty blocks with blank-line discipline (no double clutter)."""
    parts = [b.strip("\n") for b in blocks if b and b.strip()]
    sep = "\n" * (gap + 1) if gap else "\n"
    return sep.join(parts)


def cmd_name(text: str) -> str:
    """Highlight a command token (static help text only)."""
    return f"[bold {ACCENT}]{safe(text)}[/bold {ACCENT}]"


def example_line(command: str, note: str = "") -> str:
    """Show a typed example; command is highlighted, optional note is dim."""
    line = f"  [dim]›[/dim] {cmd_name(command)}"
    if note:
        line += f"\n      [dim]{safe(note)}[/dim]"
    return line


def prose_block(*paragraphs: str) -> str:
    """Plain instructional paragraphs (static; still escaped for safety)."""
    return "\n\n".join(safe(p.strip()) for p in paragraphs if p and p.strip())


def render_help(kinds: str) -> str:
    """Comprehensive in-game manual: navigate, build, concepts, examples."""
    return join_blocks(
        title_line(f"{PRODUCT_NAME} · Instruction Manual"),
        prose_block(
            "This is a walkable studio for building a multiverse. "
            "You stand inside places, carry things, and shape the world with the same "
            "prompt you use to explore. Type a command, press Enter, read the reply."
        ),
        _manual_welcome(),
        _manual_concepts(),
        _manual_navigate(),
        _manual_build(kinds),
        _manual_lore(),
        _manual_quick_ref(kinds),
        _manual_tips(),
        gap=1,
    )


def _manual_welcome() -> str:
    return join_blocks(
        rule("Start here"),
        prose_block(
            "You begin as the Builder in a seed multiverse (Material realm, Prime timeline). "
            "Open your eyes with look. Travel with go. When you are ready to invent, use dig, "
            "link, create, and spawn."
        ),
        example_line("look", "Describe the place you are in"),
        example_line("help", "Show this manual again (also: ?)"),
        gap=0,
    )


def _manual_concepts() -> str:
    return join_blocks(
        rule("Core ideas (plain language)"),
        prose_block(
            "VEN (Virtual Entity) — the prime idea of a thing: a cathedral, a person, "
            "a feeling, a material, a realm, a timeline. Primes are templates and canon.",
            "Instance — one living copy of a VEN, situated in the multiverse "
            "(this hall, now, in Memory-Archive). You walk between place instances.",
            "Containment — anything can hold anything. A room holds people and objects; "
            "a person can hold feelings or motifs. Slots name the relationship "
            "(interior, inventory, feeling, memory, …).",
            "Links (paths) — directed edges from place to place. Types include "
            "spatial, dimensional, temporal, narrative, conditional. "
            "Going “through the mirror” is a normal path, not a special engine mode.",
            "Elevate — promote a lived instance into a new Prime VEN that can spawn "
            "further instances later.",
            "Lore revisions — append-only notes on a place (or VEN), optionally tagged "
            "with a timeline or when-label, so history accumulates instead of overwriting.",
        ),
        gap=0,
    )


def _manual_navigate() -> str:
    return join_blocks(
        rule("How to navigate"),
        prose_block(
            "Navigation is about seeing where you are, what leaves this place, and moving "
            "along a path label. Partial labels work when they uniquely match."
        ),
        section("See the room"),
        example_line("look", "Title, prose, realm/timeline, paths, people, things"),
        example_line("status", "You / place / realm / timeline / inv (sit, whereami)"),
        example_line("paths", "List paths from here (exits / ways / x)"),
        example_line("who", "People present"),
        section("Move"),
        example_line("go south", "Spatial path by label"),
        example_line("go through the mirror", "Dimensional jump (seed world)"),
        example_line("go years later", "Temporal jump (from the Archive)"),
        example_line("g mirror", "Short form: g is go; partial match on “mirror”"),
        section("Carry things"),
        example_line("take silver", "Pick up Silver Thread from the floor (partial name)"),
        example_line("inv", "List inventory (also: inventory, i)"),
        example_line("drop silver", "Put it back in the current place"),
        example_line("examine archivist", "Read a person/thing; see what it contains"),
        prose_block(
            "After go, the studio prints a short travel cue, then a full look of the new place. "
            "Items in your inventory travel with you across spatial, dimensional, and temporal links."
        ),
        gap=0,
    )


def _manual_build(kinds: str) -> str:
    return join_blocks(
        rule("How to build"),
        prose_block(
            "Building never leaves the prompt. Create primes, place instances in the world, "
            "connect paths, write descriptions, and nest contents. You stay in your current "
            "place unless you dig and then link and go."
        ),
        section("Places"),
        example_line("dig Quiet Gallery", "New place VEN + instance (same realm/timeline as here)"),
        example_line(
            "link north -> Quiet Gallery both",
            "Exit from here; both = reverse exit too (default type: spatial)",
        ),
        example_line(
            "link through the tear -> Quiet Gallery dimensional both",
            "Typed link: spatial | dimensional | temporal | narrative | conditional",
        ),
        example_line(
            "@desc Soft light on unfinished canvases. Dust tastes like turpentine.",
            "Replace description (\\n for line breaks; @desc + to append)",
        ),
        example_line("undo", "Reverse the last builder action this session"),
        section("Primes, instances, and nesting"),
        example_line(
            "create material Moon Filament | Thin light that remembers tides.",
            "New prime VEN (kinds listed below)",
        ),
        example_line(
            "create object Secret Document of File | Classified…",
            "Specialization: child of parent prime File",
        ),
        example_line("spawn moon-filament", "Instance into the current place"),
        example_line("spawn moon-filament as A single strand", "Named instance override"),
        example_line("create feeling Distant Thunder | Pressure before rain."),
        example_line("spawn distant-thunder", "Feelings land in the feeling slot here"),
        example_line(
            "put Distant Thunder in The Archivist feeling",
            "Move a thing into a container with an optional slot",
        ),
        example_line(
            "elevate silver as Silver Prime",
            "Instance → new prime under origin; lived copy rebinds",
        ),
        example_line("compose Him + Concept of Him as concept", "Prime-level composition"),
        example_line("vens", "List primes; try: vens place  ·  vens tree"),
        example_line("lineage File", "Specialization path root › …"),
        example_line("kinds", f"VEN kinds: {kinds}"),
        prose_block(
            "Typical loop: dig a room → link it → go there → @desc → create/spawn furnishings "
            "→ lore add for canon over time. Use examine on people and places to check containment. "
            "For conceptual trees: create … of <parent>, elevate, compose, vens tree."
        ),
        gap=0,
    )


def _manual_lore() -> str:
    return join_blocks(
        rule("Lore and history"),
        prose_block(
            "Lore is a revision log, not a single blurb. Add entries as the place changes "
            "across your story’s timeline."
        ),
        example_line("lore", "Show revisions for the current place"),
        example_line(
            "lore add Founding | The nave was raised for market travelers.",
            "Title | body  (title optional: lore add just the body works)",
        ),
        example_line("lore search mirror", "Search titles and bodies"),
        gap=0,
    )


def _manual_quick_ref(kinds: str) -> str:
    return join_blocks(
        rule("Quick command reference"),
        _help_section(
            "Movement & senses",
            [
                ("look / l", "Describe here"),
                ("status", "You / place / layers / inv"),
                ("paths / exits / x", "List paths from here"),
                ("go / g <path>", "Travel (partial labels ok)"),
                ("inv / i", "Inventory"),
                ("take / drop", "Pick up or drop by name"),
                ("examine / exam / inspect / in", "Detail a thing here or carried"),
                ("who", "People here"),
            ],
        ),
        _help_section(
            "Lore",
            [
                ("lore", "Revisions for this place"),
                ("lore add …", "title | body  (or body alone)"),
                ("lore search …", "Search lore text"),
            ],
        ),
        _help_section(
            "Builder",
            [
                ("dig <name>", "New place VEN + instance"),
                ("link …", "<exit> -> <place> [type] [both]"),
                ("@desc …", "Show / set / + append / clear place text"),
                ("create …", "<kind> <name> [of parent] [| desc]"),
                ("spawn …", "<ven> [as name] into current place"),
                ("put …", "<thing> in <container> [slot]"),
                ("elevate …", "<thing> [as name] → rebind prime"),
                ("compose …", "whole + part [as role]"),
                ("lineage …", "root › … specialization path"),
                ("undo / u", "Undo last builder action"),
                ("vens [kind|tree]", "List primes or lineage tree"),
                ("kinds", "List VEN kinds"),
            ],
        ),
        _help_section(
            "System",
            [
                ("help / ?", "This manual"),
                ("quit / exit / q", "Leave the studio"),
            ],
        ),
        hint(f"VEN kinds: {kinds}"),
        gap=0,
    )


def _manual_tips() -> str:
    return join_blocks(
        rule("Tips"),
        prose_block(
            "Names can be partial when unique (take silver, go mirror, examine archiv).",
            "Exit labels need not be compass directions — “through grief” is valid if you link it.",
            "The same place VEN can have many instances (Prime vs Shattered halls in the seed).",
            "Ids in status and examine are for precision; day-to-day, use readable names.",
            "Type help anytime. Domain commands never require a separate editor.",
        ),
        gap=0,
    )


def _help_section(title: str, rows: list[tuple[str, str]]) -> str:
    lines = [f"[bold]{safe(title)}[/bold]"]
    for cmd, desc in rows:
        lines.append(
            f"  [bold {ACCENT}]{safe(cmd):18}[/bold {ACCENT}]  [dim]{safe(desc)}[/dim]"
        )
    return "\n".join(lines)
