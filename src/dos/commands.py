"""Parse and execute studio commands."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import format as fmt
from .dialog import (
    FIN_TOKEN,
    DialogSession,
    dialog_teaser_line,
    format_script_turn,
    format_transcript_view,
    parse_dialog_when_line,
    parse_talk_args,
    parse_when_stamp,
    person_inner_kinds,
)
from .help_topics import render_help_index, render_help_topic
from .ids import cute_name, display_name, parse_resolve_query, split_as_title
from .textutil import unescape_desc
from .world import (
    CONTAINMENT_SLOTS,
    FEELING_GROUP_KINDS,
    INNER_LIFE_KINDS,
    KINDS,
    LINK_TYPE_CODES,
    LINK_TYPES,
    SUBTYPE_KINDS,
    InstanceView,
    World,
    default_inner_slot,
    format_kind_label,
    is_inner_life_kind,
    parse_kind_spec,
)


@dataclass
class CommandResult:
    ok: bool
    message: str
    quit: bool = False
    open_book_id: str | None = None  # TUI: open soft full-width book reader
    # TUI: open soft wiki dossier reader — (query label, deep expansion)
    open_wiki: tuple[str, bool] | None = None
    clear_log: bool = False  # TUI/REPL: wipe transcript before showing message


# Short index shown by bare help / ?  (detail via help <term>)
HELP = render_help_index()

# Creator-tool shorthand (slash namespace, like dialog /fin). Long form stays.
# Other domains can use /letter without colliding with create/spawn words.
_CREATOR_SHORTHAND: dict[str, str] = {
    "/c": "create",
    "/s": "spawn",
}


def dispatch(world: World, line: str) -> CommandResult:
    line = line.strip()
    if not line:
        return CommandResult(True, "")

    # Mid-dialog: every line is a turn (or /fin) until the session closes
    if world.active_dialog is not None:
        try:
            return CommandResult(True, _dialog_input(world, line))
        except Exception as e:  # noqa: BLE001
            return CommandResult(False, fmt.err(str(e)))

    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    cmd = _CREATOR_SHORTHAND.get(cmd, cmd)

    try:
        if cmd in ("quit", "exit", "q"):
            return CommandResult(True, fmt.hint("Until the next shelf."), quit=True)
        if cmd in ("clear", "clr"):
            # Empty message + clear_log → totally blank transcript (no tips banner)
            return CommandResult(True, "", clear_log=True)
        if cmd in ("help", "?"):
            return CommandResult(True, _help(arg))
        if cmd in ("look", "l"):
            return CommandResult(True, _look(world, arg))
        if cmd == "locate":
            return CommandResult(True, _locate(world, arg))
        # Temporary aliases → locate self (retire later)
        if cmd in ("status", "sit", "situation", "whereami", "where"):
            return CommandResult(True, _locate(world, "self"))
        if cmd in ("paths", "path", "exits", "x", "ways", "waypoints", "way"):
            return CommandResult(True, _exits(world))
        if cmd in ("map", "graph"):
            return CommandResult(True, _map(world, arg))
        if cmd in ("go", "g"):
            return _go(world, arg)
        if cmd in ("run", "activate", "use", "enter"):
            return _run(world, arg, verb=cmd)
        if cmd == "unlock":
            return _unlock(world, arg)
        if cmd == "lock":
            return _lock(world, arg)
        if cmd in ("logout", "logoff", "log-out"):
            return _logout(world, arg)
        if cmd == "portal":
            return CommandResult(True, _portal(world, arg))
        if cmd in ("inv", "inventory", "i"):
            return CommandResult(True, _inv(world, arg))
        if cmd in ("take", "get"):
            return CommandResult(True, _take(world, arg))
        if cmd == "drop":
            return CommandResult(True, _drop(world, arg))
        if cmd in ("examine", "exam", "inspect", "in"):
            return CommandResult(True, _examine(world, arg))
        if cmd == "wiki":
            return _wiki(world, arg)
        if cmd == "who":
            return CommandResult(True, _who(world))
        if cmd == "talk":
            return CommandResult(True, _talk(world, arg))
        if cmd in ("dialogs", "dialog"):
            return CommandResult(True, _dialogs(world, arg))
        if cmd == "lore":
            return CommandResult(True, _lore(world, arg))
        if cmd in ("folio", "book"):
            # folio is the product verb; book remains a full alias
            return _book_cmd(world, arg)
        if cmd == "read":
            # read <folio> shorthand
            return _book_cmd(world, f"open {arg}" if arg else "open")
        if cmd == "open":
            # open door/room portal · or open folio (smart)
            return _open_smart(world, arg)
        if cmd == "dig":
            return CommandResult(True, _dig(world, arg))
        if cmd == "link":
            return CommandResult(True, _link(world, arg))
        if cmd in ("unlink", "delink"):
            return CommandResult(True, _unlink(world, arg))
        if cmd == "@desc":
            return CommandResult(True, _desc(world, arg))
        if cmd == "text":
            return CommandResult(True, _text_cmd(world, arg))
        if cmd == "print":
            return CommandResult(True, _print_cmd(world, arg))
        if cmd == "create":
            return CommandResult(True, _create(world, arg))
        if cmd == "spawn":
            return CommandResult(True, _spawn(world, arg))
        if cmd in ("rename", "call"):
            return CommandResult(True, _rename(world, arg))
        if cmd in ("instances", "inst"):
            return CommandResult(True, _instances(world, arg))
        if cmd == "history":
            return CommandResult(True, _history(world, arg))
        if cmd in ("retime", "retimes", "when-set"):
            return CommandResult(True, _retime(world, arg))
        if cmd in ("put", "install"):
            return CommandResult(True, _put(world, arg))
        if cmd in ("despawn", "lose"):
            return CommandResult(True, _despawn(world, arg))
        if cmd in ("reclaim", "unlose", "findlost"):
            return CommandResult(True, _reclaim(world, arg))
        if cmd == "lost":
            return CommandResult(True, _lost_list(world, arg))
        if cmd == "elevate":
            return CommandResult(True, _elevate(world, arg))
        if cmd == "vens":
            return CommandResult(True, _list_vens(world, arg))
        if cmd == "ven":
            return CommandResult(True, _ven_cmd(world, arg))
        if cmd == "lineage":
            return CommandResult(True, _lineage(world, arg))
        if cmd == "compose":
            return CommandResult(True, _compose(world, arg))
        if cmd in ("timeline", "timelines", "tl"):
            return CommandResult(True, _timeline(world, arg))
        if cmd in ("realm", "realms"):
            return CommandResult(True, _realm(world, arg))
        if cmd in ("undo", "u"):
            return CommandResult(True, _undo(world))
        if cmd == "kinds":
            return CommandResult(True, fmt.hint("VEN kinds: " + ", ".join(KINDS)))
        return CommandResult(
            False,
            fmt.err(f"Unknown command {cmd!r}.") + "  " + fmt.hint("Type help."),
        )
    except Exception as e:  # noqa: BLE001 — surface to player
        return CommandResult(False, fmt.err(str(e)))


def _look_ven_label(inst: InstanceView) -> str | None:
    """Prime VEN name for look lists when the instance title differs from the prime."""
    ven = display_name(inst.ven_name or "")
    if not ven:
        return None
    inst_name = display_name(inst.name or "")
    # Same name → kind alone is enough; retitled spawn → show source prime
    if inst_name.casefold() == ven.casefold():
        return None
    return ven


def _presence_code(world: World | None, inst: InstanceView) -> str:
    """Instance short ref (THG-001-0001) for call/disambiguate; falls back to ven code."""
    if world is not None:
        try:
            if world.is_tdf(inst.id):
                payload = world.tdf_payload(inst.id) or {}
                tdf = (payload.get("code") or "").strip()
                if tdf:
                    return tdf
            return world.short_ref_of(inst.id)
        except Exception:  # noqa: BLE001
            pass
    return (inst.ven_code or "—").strip() or "—"


def _tdf_data_display(world: World | None, inst: InstanceView) -> str:
    """
    Human contents for a ticket slip column (range / due / raw).

    Empty for non-TDFs so the data column can collapse when unused.
    """
    if world is None or not world.is_tdf(inst.id):
        return ""
    payload = world.tdf_payload(inst.id) or {}
    data = payload.get("data") or {}
    start = (data.get("start") or "").strip()
    end = (data.get("end") or "").strip()
    if start and end:
        return f"{start} → {end}"
    if start:
        return start
    raw = (data.get("raw") or data.get("when") or "").strip()
    return raw


def _presence_row(
    inst: InstanceView, *, world: World | None = None
) -> tuple[str, str, str, str, str]:
    """
    Plain columns for look / examine lists::

      prime · name · data · code · color_kind

    Prime = origin VEN name; name = lived title; data = TDF contents (range…);
    code = instance short ref / TDF-########.
    TDFs show subtype as prime chip, range in data, TDF code as code.
    """
    name = display_name(inst.name or "")
    kind = (inst.ven_kind or "other").strip() or "other"
    prime = display_name(inst.ven_name or "") or "—"
    data = ""
    if world is not None and world.is_tdf(inst.id):
        payload = world.tdf_payload(inst.id) or {}
        sub = (payload.get("subtype") or "").strip()
        k = (payload.get("kind") or "").strip()
        if sub and k:
            prime = f"ticket/{sub}:{k}"
        elif sub:
            prime = f"ticket/{sub}"
        else:
            prime = "ticket"
        data = _tdf_data_display(world, inst)
    code = _presence_code(world, inst)
    return prime, name, data, code, kind


def _presence_column_widths(
    sections: list[tuple[str, list[InstanceView]]],
    *,
    world: World | None = None,
    deep: bool = False,
) -> tuple[int, int, int, int]:
    """Widest PRIME / NAME / DATA / CODE across every non-empty section.

    *data* width is 0 when no row carries TDF contents (column omitted).
    """
    primes: list[str] = []
    names: list[str] = []
    datas: list[str] = []
    codes: list[str] = []

    def _collect(inst: InstanceView) -> None:
        p, n, d, c, _ = _presence_row(inst, world=world)
        primes.append(p)
        names.append(n)
        datas.append(d)
        codes.append(c)

    for _, items in sections:
        for inst in items:
            _collect(inst)
            if deep and world is not None and _is_placement_bin(inst):
                for ch in world.contents(inst.id):
                    _collect(ch)
    if not names:
        return 4, 4, 0, 8
    w_data = max((len(x) for x in datas), default=0)
    # Only reserve a data column when something actually has contents
    if not any(datas):
        w_data = 0
    return (
        max(len(x) for x in primes),
        max(len(x) for x in names),
        w_data,
        max(len(x) for x in codes),
    )


def _is_placement_bin(inst: InstanceView) -> bool:
    """Root kind ``bin`` (legacy ``container``) forms a named placement bucket."""
    from .world import BIN_KINDS

    return (inst.ven_kind or "").strip().lower() in BIN_KINDS


def _placement_sections(
    world: World,
    parent_id: str,
    *,
    exclude_ids: set[str] | None = None,
    kids: list[InstanceView] | None = None,
    loose_label: str = "Here",
) -> list[tuple[str, list[InstanceView], bool]]:
    """
    Placement buckets for look / examine / inv (not kind taxonomy).

    - Non-bins among *parent*'s direct children → section *loose_label* (default **Here**)
    - Each **bin** among direct children → section named after that instance,
      listing **its** direct children only (shallow). Empty bins still
      appear (``show_if_empty`` True) so furniture is visible when bare.

    *kids*: optional pre-filtered child list (e.g. inventory slot only).
    Nested bins are *rows* under a parent bucket on look; when you
    ``examine`` the parent, those nested bins become their own opened
    buckets (same function, parent_id = table).
    """
    skip = exclude_ids or set()
    if kids is None:
        child_list = [c for c in world.contents(parent_id) if c.id not in skip]
    else:
        child_list = [c for c in kids if c.id not in skip]
    loose: list[InstanceView] = []
    bins: list[InstanceView] = []
    for c in child_list:
        if _is_placement_bin(c):
            bins.append(c)
        else:
            loose.append(c)
    out: list[tuple[str, list[InstanceView], bool]] = []
    if loose:
        out.append((fmt.section(loose_label), loose, False))
    for b in bins:
        header = _bin_bucket_header(b, world=world)
        inner = list(world.contents(b.id))
        out.append((header, inner, True))
    return out


def _bin_bucket_header(
    inst: InstanceView,
    *,
    indent: int = 0,
    nested: bool = False,
    world: World | None = None,
) -> str:
    """
    Bin section title: lived name + light prime + short ref code.

    *nested*: inner bin under a parent bucket (``--deep``) — tree mark + indent
    so it reads as a bin, not a list row.
    """
    name = display_name(inst.name or "Bin")
    ven = display_name(inst.ven_name or "")
    code = _presence_code(world, inst)
    bits: list[str] = []
    if ven:
        bits.append(ven)
    if code and code != "—":
        bits.append(code)
    lead = " " * max(0, indent)
    if nested:
        lead += "[dim]└─[/dim] "
    if not bits:
        return f"{lead}[bold]{fmt.safe(name)}[/bold]"
    trail = " · ".join(bits)
    return (
        f"{lead}[bold]{fmt.safe(name)}[/bold]"
        f"  [dim]· {fmt.safe(trail)}[/dim]"
    )


def _format_presence_line(
    inst: InstanceView,
    *,
    w_prime: int,
    w_name: int,
    w_data: int,
    w_code: int,
    world: World | None = None,
    indent: int = 2,
) -> str:
    """One presence row: prime · name · [data] · code (+ optional slot)."""
    gap = "  "
    prime, name, data, code, color_kind = _presence_row(inst, world=world)
    line = (
        f"{' ' * indent}"
        f"[dim]{fmt.safe(fmt.pad_visible(prime, w_prime))}[/dim]{gap}"
        f"{fmt.colored_padded_name(name, color_kind, w_name)}{gap}"
    )
    if w_data > 0:
        # Ticket contents (range / due) — dim; non-tickets pad blank (no dash noise)
        cell = data if data else ""
        line += f"[dim]{fmt.safe(fmt.pad_visible(cell, w_data))}[/dim]{gap}"
    line += f"[dim]{fmt.safe(fmt.pad_visible(code, w_code))}[/dim]"
    if world is not None:
        # Slot only when non-default (feeling, worn, …). interior + inventory
        # are the usual "in this list" slots — no trailer. No "run" badge.
        slot_row = world.container_of(inst.id)
        slot = (slot_row[1] if slot_row else "") or ""
        if slot and slot not in ("interior", "inventory"):
            line += f"{gap}[dim]{fmt.safe(slot)}[/dim]"
    return line


def _format_presence_section(
    section_header: str,
    items: list[InstanceView],
    *,
    w_prime: int,
    w_name: int,
    w_data: int,
    w_code: int,
    show_if_empty: bool = False,
    world: World | None = None,
    deep: bool = False,
) -> str | None:
    """
    One placement block — shared column grid::

      Here
        Soft Ache      Soft Ache      SNS-001-0001

      Table  · Table · BIN-001-0001
        Here
          Coffee Cup     Coffee     THG-001-0002   ← root / not-in-bin first
                                                ← blank line
        └─ Drawer  · Drawer · BIN-002-0001
            Spoon      Spoon      THG-003-0001

    Columns: prime · name · [data] · code. *data* (ticket range/due) only when
    any row in the shared grid carries TDF contents.
    Loose items always list before nested bins (blank line between).
    *deep*: each listed **bin** becomes a nested bin header with its
    contents underneath (one layer only).
    """
    if not items:
        if not show_if_empty:
            return None
        return f"{section_header}\n  [dim](empty)[/dim]"

    loose = [i for i in items if not _is_placement_bin(i)]
    nested_bins = [i for i in items if _is_placement_bin(i)]

    lines = [section_header]

    def _row(inst: InstanceView, indent: int = 2) -> str:
        return _format_presence_line(
            inst,
            w_prime=w_prime,
            w_name=w_name,
            w_data=w_data,
            w_code=w_code,
            world=world,
            indent=indent,
        )

    # Root / not-in-a-bin first
    if loose:
        if nested_bins:
            lines.append("  [dim]Here[/dim]")
        for inst in loose:
            lines.append(_row(inst, 2 if not nested_bins else 4))

    if loose and nested_bins:
        lines.append("")  # blank line between root and bins

    for inst in nested_bins:
        if deep and world is not None:
            lines.append(
                _bin_bucket_header(inst, indent=2, nested=True, world=world)
            )
            kids = list(world.contents(inst.id))
            if not kids:
                lines.append("      [dim](empty)[/dim]")
            else:
                for ch in kids:
                    lines.append(_row(ch, 6))
        else:
            lines.append(_row(inst, 2))

    return "\n".join(lines)


def _format_look_presence_blocks(
    sections: list[tuple[str, list[InstanceView]]]
    | list[tuple[str, list[InstanceView], bool]],
    *,
    world: World | None = None,
    deep: bool = False,
) -> list[str | None]:
    """Format placement sections with one shared column grid."""
    normalized: list[tuple[str, list[InstanceView], bool]] = []
    for entry in sections:
        if len(entry) == 3:
            title, items, show_empty = entry  # type: ignore[misc]
        else:
            title, items = entry  # type: ignore[misc]
            show_empty = False
        normalized.append((title, list(items), bool(show_empty)))
    active = [
        (t, items, se)
        for t, items, se in normalized
        if items or se
    ]
    if not active:
        return []
    width_src = [(t, items) for t, items, _ in active if items]
    if width_src:
        w_prime, w_name, w_data, w_code = _presence_column_widths(
            width_src, world=world, deep=deep
        )
    else:
        w_prime, w_name, w_data, w_code = 4, 4, 0, 8
    return [
        _format_presence_section(
            title,
            items,
            w_prime=w_prime,
            w_name=w_name,
            w_data=w_data,
            w_code=w_code,
            show_if_empty=show_empty,
            world=world,
            deep=deep,
        )
        for title, items, show_empty in active
    ]


def _placement_has_runnable(
    world: World, sections: list, *, deep: bool = False
) -> bool:
    """True if any listed instance (or deep child) is portal-ready."""
    for entry in sections:
        items = entry[1] if len(entry) > 1 else []
        for inst in items or []:
            if world.get_portal_to(inst.id):
                return True
            if deep and _is_placement_bin(inst):
                for ch in world.contents(inst.id):
                    if world.get_portal_to(ch.id):
                        return True
    return False


def _layer_name_markup(name: str | None, kind: str) -> str:
    """Colored realm/timeline name, or dim dash if missing."""
    n = (name or "").strip()
    if not n or n == "—":
        return "[dim]—[/dim]"
    return fmt.colored_name(display_name(n), kind)


def _kind_subtype_trailer(inst: InstanceView) -> str:
    """
    Kind chip for examine headers (and non-look contexts).

    When a subtype exists: ``place: app`` (colon, readable).
    Otherwise bare kind: ``place``.
    """
    kind = (inst.ven_kind or "other").strip() or "other"
    sub = (inst.ven_subtype or "").strip()
    if sub:
        return f"{kind}: {sub}"
    return kind


def _instance_context_details(world: World, inst: InstanceView) -> str:
    """kind[: subtype] | realm | timeline — trailer after a location name."""
    kind_lbl = _kind_subtype_trailer(inst)
    coords = world.coords_of(inst)
    r = _layer_name_markup(coords.get("realm_name"), "realm")
    t = _layer_name_markup(coords.get("timeline_name"), "timeline")
    return (
        f"{fmt.kind_label(kind_lbl)}"
        f"  [dim]|[/dim]  {r}"
        f"  [dim]|[/dim]  {t}"
    )


def _location_header_line(world: World, inst: InstanceView) -> str:
    """
    Look lead-in — omit root kind ``place``; subtype only when set::

        Location: Mailroom · app  |  Realm  |  Timeline
        Location: The Void · Realm  |  Timeline
    """
    name = fmt.title_line(inst.name, kind="place")
    coords = world.coords_of(inst)
    r = _layer_name_markup(coords.get("realm_name"), "realm")
    t = _layer_name_markup(coords.get("timeline_name"), "timeline")
    sub = (inst.ven_subtype or "").strip()
    if sub:
        details = (
            f"{fmt.kind_label(sub)}"
            f"  [dim]|[/dim]  {r}"
            f"  [dim]|[/dim]  {t}"
        )
    else:
        details = f"{r}  [dim]|[/dim]  {t}"
    return f"[bold]Location:[/bold] {name}  [dim]·[/dim]  {details}"


def _instance_context_line(world: World, inst: InstanceView) -> str:
    """Under-title strip (examine etc.): kind[/subtype] | realm | timeline."""
    return _instance_context_details(world, inst)


def _session_hint_line(world: World) -> str | None:
    session = world.peek_portal_session()
    if session is None:
        return None
    app_n = display_name(str(session.get("app_name") or "app"))
    ret = world.get_instance(str(session.get("return_place_id") or ""))
    ret_n = display_name(ret.name) if ret else "where you ran from"
    return fmt.hint(f"session · {app_n}  ·  logout → {ret_n}")


# English glue for look → examine (longest first so ``into`` wins over ``in``)
_LOOK_PREPOSITIONS: tuple[str, ...] = (
    "inside",
    "into",
    "onto",
    "upon",
    "under",
    "within",
    "through",
    "at",
    "in",
    "on",
)


def _peel_leading_article(name: str) -> str:
    """``the brass door`` → ``brass door`` (soft English)."""
    raw = (name or "").strip()
    low = raw.lower()
    for art in ("the ", "a ", "an "):
        if low.startswith(art):
            return raw[len(art) :].strip()
    return raw


def _peel_look_target(arg: str) -> str:
    """
    Optional English glue into examine::

      at door · in drawer · into pack · on table · inside box
      look the door  (also strips a leading article)
    """
    raw = (arg or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    # bare preposition alone → no target (fall through to room look)
    if low in _LOOK_PREPOSITIONS:
        return ""
    for prep in _LOOK_PREPOSITIONS:
        prefix = prep + " "
        if low.startswith(prefix):
            return _peel_leading_article(raw[len(prefix) :].strip())
    return _peel_leading_article(raw)


def _look(world: World, arg: str = "") -> str:
    """
    look                 — room view (lore count hint if any)
    look deep / --deep   — room view + bin contents one layer deeper + full place lore
    look at|in|on X      — same as examine X (also into/inside/onto/…)
    look [--deep] at X   — examine X with full lore / deeper bins
    look X deep          — examine X with full lore + deeper bins
    """
    from .wiki import parse_deep_flag

    target, deep = parse_deep_flag(arg)
    target = _peel_look_target(target)
    if target:
        return _examine(world, target, deep=deep)

    loc = world.player_location()
    if not loc:
        return fmt.hint("You are nowhere. (No player location.)")
    info = world.describe_place(loc)

    # Location: name · kind | realm | timeline → session → desc → rest
    header = _location_header_line(world, loc)
    session_line = _session_hint_line(world)
    body = fmt.prose(loc.description)

    # Paths inline (same grouping as `paths`); empty rooms stay quiet
    exits = list(info["exits"] or [])
    if exits:
        exit_block: str | None = _format_paths_block(world, exits)
    else:
        exit_block = fmt.hint("No paths from here.")

    # Placement: Here = loose in room; each bin VEN is its own bucket
    # (shallow kids). --deep expands each listed bin one more layer.
    pid = world.player_id()
    exclude = {pid} if pid else set()
    placement = _placement_sections(world, loc.id, exclude_ids=exclude)
    presence_blocks = _format_look_presence_blocks(
        placement, world=world, deep=deep
    )

    lore_block = None
    lore_rows = list(info["lore"] or [])
    if deep:
        if lore_rows:
            lore_block = _format_lore_rows(f"Lore · {loc.name}", lore_rows)
        else:
            lore_block = fmt.hint("No lore revisions for this place.")
    elif lore_rows:
        n = len(lore_rows)
        lore_block = fmt.hint(f"{n} lore revision(s) — type lore  ·  look --deep")

    head = fmt.join_blocks(header, session_line, gap=0)
    return fmt.join_blocks(
        head,
        body,
        exit_block,
        *presence_blocks,
        lore_block,
        gap=1,
    )


def _locate(world: World, arg: str) -> str:
    """
    locate self          — avatar where-now (place, layers, inv)
    locate               — same as locate self
    locate <code|name>   — later: find instances of a VEN / short ref
    """
    from .status import format_status_command

    target = (arg or "").strip()
    low = target.lower()
    if not target or low in ("self", "me", "i", "you", "player", "avatar"):
        return format_status_command(world)
    return fmt.hint(
        f"locate {target!r} is not wired yet.\n"
        "  Today:  locate self  ·  locate  (same — where your avatar is)\n"
        "  Later:  locate THG-001  ·  locate <prime|short-ref>  "
        "(instances of a VEN / code in the world)"
    )


def _coords_label(coords: dict) -> str:
    """Human-readable realm / timeline coords line."""
    from .ids import display_name

    r = coords.get("realm_name") or "—"
    t = coords.get("timeline_name") or "—"
    if r != "—":
        r = display_name(r)
    if t != "—":
        t = display_name(t)
    return f"{r} / {t}"


def _path_type_code(link_type: str) -> str:
    """Two-letter path type prefix (sp, di, te, na, co)."""
    t = (link_type or "spatial").strip().lower() or "spatial"
    code = LINK_TYPE_CODES.get(t)
    if code:
        return code
    bare = re.sub(r"[^a-z]", "", t)[:2] or "??"
    return f"{bare:<2}"[:2]


def _format_paths_block(world: World, exits: list) -> str:
    """
    Flat path list with type shorthand on each row::

        Paths
          sp · east → Place Name
          di · through the mirror → Hall of Shelved Years
    """
    type_rank = {t: i for i, t in enumerate(LINK_TYPES)}
    # (rank, label_key, type, code, label, dname, dkind)
    rows: list[tuple[int, str, str, str, str, str, str]] = []
    for ex in exits:
        t = (ex["link_type"] or "spatial").strip().lower() or "spatial"
        dest = world.get_instance(ex["to_instance_id"])
        dname = dest.name if dest else "?"
        dkind = (dest.ven_kind if dest else "place") or "place"
        label = (ex["label"] or "?").strip() or "?"
        rows.append(
            (
                type_rank.get(t, 100),
                label.lower(),
                t,
                _path_type_code(t),
                label,
                dname,
                dkind,
            )
        )
    rows.sort(key=lambda r: (r[0], r[1]))

    lines: list[str] = [fmt.section("Paths")]
    for _rank, _lk, t, code, label, dname, dkind in rows:
        color = fmt.LINK_TYPE_COLORS.get(t, fmt.MUTED)
        code_mk = f"[bold {color}]{fmt.safe(code)}[/bold {color}]"
        lines.append(
            f"  {code_mk} [dim]·[/dim] {fmt.safe(label)}  →  "
            f"{fmt.colored_name(dname, dkind)}"
        )
    return "\n".join(lines)


def _exits(world: World) -> str:
    """List paths (place→place links) from here. Aliases: paths, exits, ways, x."""
    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")
    exits = world.exits(loc.id)
    if not exits:
        return fmt.hint("No paths from here.")
    return _format_paths_block(world, exits)


def _map(world: World, arg: str) -> str:
    """Local multiverse map: exit tree from here, depth-limited, link types colored."""
    from .mapview import collect_map_tree, format_map_tree, parse_map_args

    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")
    depth, err = parse_map_args(arg)
    if err:
        return fmt.hint(err)
    tree = collect_map_tree(world, loc.id, depth=depth)
    return format_map_tree(tree)


def _go(world: World, arg: str) -> CommandResult:
    if not arg:
        return CommandResult(True, fmt.hint("Go where?  Usage: go <path label>"))
    loc = world.player_location()
    if not loc:
        return CommandResult(True, fmt.hint("Nowhere."))
    ex = world.find_exit(loc.id, arg)
    if not ex:
        return CommandResult(True, fmt.err(f"No path matching {arg!r}."))
    world.move_player(ex["to_instance_id"])
    travel = fmt.hint(f"→ {ex['label']}")
    # Fresh scene: clear transcript so play is not buried under builder history
    return CommandResult(
        True,
        fmt.join_blocks(travel, _look(world), gap=1),
        clear_log=True,
    )


def _names_match_thing(query: str, inst: InstanceView) -> bool:
    from .ids import names_match

    return (
        names_match(query, inst.name or "")
        or names_match(query, inst.ven_name or "")
        or names_match(query, inst.ven_slug or "")
    )


def _portal(world: World, arg: str) -> str:
    """
    portal <app> -> <place>     bind object run-portal to a place
    portal clear <app>          remove binding
    """
    raw = (arg or "").strip()
    if not raw:
        return fmt.hint(
            "Usage: portal <app> -> <place>\n"
            "       portal clear <app>\n"
            "  Bind an installed object to a place world.  "
            "run travels there; not listed under paths."
        )
    low = raw.lower()
    if low.startswith("clear ") or low.startswith("off ") or low.startswith("unset "):
        app_q = raw.split(maxsplit=1)[1].strip()
        app, err = _resolve_one(world, app_q)
        if err or app is None:
            # allow unique global
            found = world.find_instances_by_name(app_q)
            if len(found) == 1:
                app = found[0]
            else:
                return err or fmt.err(f"No {app_q!r} to clear portal on.")
        prior = world.get_portal_to(app.id)
        world.set_portal_to(app.id, None)
        iid = app.id

        def undo_clear(w: World, instance_id: str = iid, old=prior) -> None:
            if old:
                w.set_portal_to(instance_id, old)
            else:
                w.set_portal_to(instance_id, None)

        world.undo_stack.push(f"portal clear {app.name}", undo_clear)
        return fmt.ok(f"Portal cleared · {display_name(app.name)}")

    if "->" not in raw:
        return fmt.hint("Usage: portal <app> -> <place>  ·  portal clear <app>")
    left, right = raw.split("->", 1)
    app_q, place_q = left.strip(), right.strip()
    if not app_q or not place_q:
        return fmt.hint("Usage: portal <app> -> <place>")
    app, err = _resolve_one(world, app_q)
    if err or app is None:
        found = world.find_instances_by_name(app_q)
        if len(found) == 1:
            app = found[0]
        elif len(found) > 1:
            return _format_ambiguous(world, app_q, found)
        else:
            return err or fmt.err(f"No app/object matching {app_q!r}.")
    assert app is not None
    # Destination: place by name (not required to be adjacent)
    places = world.find_instances_by_name(place_q, kind="place")
    if not places:
        return fmt.err(f"No place matching {place_q!r}.  dig one first.")
    if len(places) > 1:
        return _format_ambiguous(world, place_q, places)
    dest = places[0]
    prior = world.get_portal_to(app.id)
    world.set_portal_to(app.id, dest.id)
    iid = app.id

    def undo_portal(w: World, instance_id: str = iid, old=prior) -> None:
        w.set_portal_to(instance_id, old)

    world.undo_stack.push(f"portal {app.name} → {dest.name}", undo_portal)
    return fmt.join_blocks(
        fmt.ok(f"Portal · {display_name(app.name)} → {display_name(dest.name)}"),
        fmt.hint(
            f"Binding lives on the token (survives take/drop).  "
            f"Apps: put/install {app.name} in <device> · run {app.name}  ·  "
            f"Doors: lock {app.name} with <key> · unlock · open / enter  ·  "
            f"Clear: portal clear {app.name}"
        ),
        gap=0,
    )


def _split_with_key(arg: str) -> tuple[str, str | None]:
    """Split ``door with key`` → (door, key). Bare door → (door, None)."""
    raw = (arg or "").strip()
    if not raw:
        return "", None
    low = raw.lower()
    if " with " in low:
        idx = low.rfind(" with ")
        left = raw[:idx].strip()
        right = raw[idx + 6 :].strip() or None
        return left, right
    return raw, None


def _resolve_portal_token(
    world: World, name: str
) -> tuple[InstanceView | None, str | None]:
    """Resolve a portal door/app token here (must already have a portal bind)."""
    q = (name or "").strip()
    if not q:
        return None, fmt.hint("Name a portal token (door, app, …).")
    hits = [
        c
        for c in world.resolve_here_candidates()
        if _names_match_thing(q, c) and world.get_portal_to(c.id)
    ]
    if not hits:
        # allow pre-bind resolve for lock authoring on any here thing
        hits = [
            c
            for c in world.resolve_here_candidates()
            if _names_match_thing(q, c)
        ]
        if not hits:
            return None, fmt.err(f"No {q!r} here.")
        if len(hits) > 1:
            return None, _format_ambiguous(world, q, hits)
        return hits[0], None
    if len(hits) > 1:
        return None, _format_ambiguous(world, q, hits)
    return hits[0], None


def _find_keys_for_portal(
    world: World, portal: InstanceView, key_q: str | None
) -> list[InstanceView]:
    """Keys in reach that fit this portal (instance bind preferred)."""
    need_inst = world.get_portal_key_instance_id(portal.id)
    need_ven = world.get_portal_key_ven_id(portal.id)
    cands = world.resolve_here_candidates()
    if key_q:
        cands = [c for c in cands if _names_match_thing(key_q, c)]
    out: list[InstanceView] = []
    for c in cands:
        if c.id == portal.id:
            continue
        if need_inst:
            if c.id == need_inst:
                out.append(c)
        elif need_ven:
            if c.ven_id == need_ven:
                out.append(c)
        elif key_q:
            # named key but portal has no bind yet
            out.append(c)
    return out


# lock -d / --desc "flavor when open fails while locked"
_LOCK_FLAG_ALIASES: dict[str, str] = {
    "desc": "desc",
    "description": "desc",
    "d": "desc",
    "deny": "desc",
    "message": "desc",
    "msg": "desc",
}


def _portal_locked_refusal(
    world: World, app: InstanceView, *, verb: str = "open"
) -> CommandResult:
    """
    Refuse open/run/enter while locked — narrative, not a red command error.

    Author -d flavor (if any) as prose; unlock hint as dim tip.
    """
    v = (verb or "open").strip() or "open"
    if world.portal_requires_key(app.id):
        klabel = world.portal_key_label(app.id)
        tip = (
            f"{display_name(app.name)} is locked.  "
            f"unlock {app.name} with {klabel}  ·  then {v} {app.name}"
        )
    else:
        tip = (
            f"{display_name(app.name)} is locked.  "
            f"unlock {app.name}  ·  then {v} {app.name}"
        )
    deny = world.get_portal_lock_deny(app.id)
    if deny:
        # Story first, soft how-to second (no red — this is fiction, not "no folio")
        return CommandResult(
            False,
            fmt.join_blocks(fmt.prose_block(deny), fmt.hint(tip), gap=1),
        )
    return CommandResult(False, fmt.join_blocks(fmt.prose_block(tip), gap=0))


def _lock(world: World, arg: str) -> CommandResult:
    """
    lock <door> [with <key>] [-d "refuse line"]

    Mark a portal token locked. Optional key VEN bind (any instance of that
    prime unlocks). ``-d`` / ``--desc`` sets the line printed when open/run
    hits the lock without unlocking first. Does not travel.
    """
    from .argflags import parse_named_flags

    raw = (arg or "").strip()
    deny_text: str | None = None
    if raw:
        parsed = parse_named_flags(raw, aliases=_LOCK_FLAG_ALIASES)
        if parsed.error:
            return CommandResult(False, fmt.err(parsed.error))
        if "desc" in parsed.flags:
            deny_text = parsed.get("desc") or ""
        rest = " ".join(parsed.positionals).strip()
    else:
        rest = ""

    door_q, key_q = _split_with_key(rest)
    if not door_q:
        return CommandResult(
            True,
            fmt.hint(
                "Usage: lock <door>  ·  lock <door> with <key>\n"
                '  lock <door> with <key> -d "The latch laughs at bare hands."\n'
                "  Then: unlock <door> [with <key>]  ·  open <door>"
            ),
        )
    door, err = _resolve_portal_token(world, door_q)
    if err or door is None:
        return CommandResult(False if err and "No " in (err or "") else True, err or "")
    if not world.get_portal_to(door.id):
        return CommandResult(
            False,
            fmt.err(
                f"{display_name(door.name)} has no portal.  "
                f"portal {door.name} -> <place> first."
            ),
        )

    prior_locked = world.is_portal_locked(door.id)
    prior_key_inst = world.get_portal_key_instance_id(door.id)
    prior_key_ven = world.get_portal_key_ven_id(door.id)
    prior_deny = world.get_portal_lock_deny(door.id)
    key_used: InstanceView | None = None

    if key_q:
        keys = [
            c
            for c in world.resolve_here_candidates()
            if _names_match_thing(key_q, c) and c.id != door.id
        ]
        if not keys:
            return CommandResult(
                False, fmt.err(f"No key {key_q!r} here to bind.")
            )
        if len(keys) > 1:
            return CommandResult(False, _format_ambiguous(world, key_q, keys))
        key_used = keys[0]
        # Bind this *copy* (named spawn), not the Key prime
        world.set_portal_key_instance_id(door.id, key_used.id)

    world.set_portal_locked(door.id, True)
    if deny_text is not None:
        # Explicit -d (including empty string to clear)
        world.set_portal_lock_deny(door.id, deny_text or None)
    iid = door.id

    def undo_lock(
        w: World,
        instance_id: str = iid,
        was_locked: bool = prior_locked,
        old_key_inst: str | None = prior_key_inst,
        old_key_ven: str | None = prior_key_ven,
        old_deny: str | None = prior_deny,
    ) -> None:
        w.set_portal_locked(instance_id, was_locked)
        w.set_portal_key_instance_id(instance_id, old_key_inst)
        if old_key_inst is None:
            w.set_portal_key_ven_id(instance_id, old_key_ven)
        w.set_portal_lock_deny(instance_id, old_deny)

    world.undo_stack.push(f"lock {door.name}", undo_lock)
    kname = display_name(key_used.name) if key_used else None
    bits = [f"Locked · {display_name(door.name)}"]
    if kname:
        bits.append(f"only {kname}")
    if deny_text is not None and deny_text.strip():
        bits.append("deny line set")
    elif deny_text is not None:
        bits.append("deny line cleared")
    main = fmt.ok("  ·  ".join(bits))
    if kname:
        tip = fmt.hint(
            f"unlock {door.name} with {key_used.name if key_used else 'key'}  ·  "
            f"then open {door.name}  ·  (this key copy only)"
        )
    else:
        tip = fmt.hint(
            f"unlock {door.name}  ·  open {door.name}  ·  "
            f"lock {door.name} with <key> to require a specific key"
        )
    if deny_text is not None and deny_text.strip():
        tip = fmt.join_blocks(
            tip,
            fmt.hint("open without the key prints your -d line first"),
            gap=0,
        )
    return CommandResult(True, fmt.join_blocks(main, tip, gap=0))


def _unlock(world: World, arg: str) -> CommandResult:
    """
    unlock <door> [with <key>]

    Clear portal lock only (does not enter). If a key VEN is bound, a matching
    key must be in reach (or named with). Keyless locks unlock bare.
    """
    door_q, key_q = _split_with_key(arg)
    if not door_q:
        return CommandResult(
            True,
            fmt.hint(
                "Usage: unlock <door>  ·  unlock <door> with <key>\n"
                "  Then open / enter / run to go through.  "
                "lock <door> with <key> to set up."
            ),
        )
    door, err = _resolve_portal_token(world, door_q)
    if err or door is None:
        return CommandResult(False if err and "No " in (err or "") else True, err or "")
    if not world.get_portal_to(door.id):
        return CommandResult(
            False,
            fmt.err(
                f"{display_name(door.name)} has no portal.  "
                f"portal {door.name} -> <place> first."
            ),
        )

    if not world.is_portal_locked(door.id):
        return CommandResult(
            True,
            fmt.join_blocks(
                fmt.ok(f"Already unlocked · {display_name(door.name)}"),
                fmt.hint(f"open / enter {door.name}  ·  lock {door.name} to re-lock"),
                gap=0,
            ),
        )

    need = world.portal_requires_key(door.id)
    key_used: InstanceView | None = None
    if need:
        keys = _find_keys_for_portal(world, door, key_q)
        if not keys:
            if key_q:
                return CommandResult(
                    False,
                    fmt.err(
                        f"{key_q!r} is not the key for "
                        f"{display_name(door.name)}."
                    ),
                )
            klabel = world.portal_key_label(door.id)
            return CommandResult(
                False,
                fmt.err(
                    f"{display_name(door.name)} is locked.  "
                    f"Need {klabel} in reach.  "
                    f"unlock {door.name} with <key>"
                ),
            )
        if len(keys) > 1 and key_q is None:
            lines = [
                fmt.err(
                    f"Several keys fit {display_name(door.name)}.  Be specific:"
                )
            ]
            for k in keys:
                lines.append(fmt.hint(f"  unlock {door.name} with {k.name}"))
            return CommandResult(False, "\n".join(lines))
        if len(keys) > 1 and key_q:
            return CommandResult(False, _format_ambiguous(world, key_q, keys))
        key_used = keys[0]
        if not world.portal_key_matches(door.id, key_used):
            return CommandResult(
                False,
                fmt.err(
                    f"{display_name(key_used.name)} does not fit "
                    f"{display_name(door.name)}."
                ),
            )
    elif key_q:
        # keyless lock but user named a key — ignore, still unlock
        pass

    prior_locked = True
    world.set_portal_locked(door.id, False)
    iid = door.id

    def undo_unlock(
        w: World, instance_id: str = iid, was_locked: bool = prior_locked
    ) -> None:
        w.set_portal_locked(instance_id, was_locked)

    world.undo_stack.push(f"unlock {door.name}", undo_unlock)
    if key_used:
        main = fmt.ok(
            f"Unlocked · {display_name(door.name)}  ·  with "
            f"{display_name(key_used.name)}"
        )
    else:
        main = fmt.ok(f"Unlocked · {display_name(door.name)}")
    tip = fmt.hint(f"open / enter {door.name}  ·  logout later to return")
    return CommandResult(True, fmt.join_blocks(main, tip, gap=0))


def _portal_binding_hint(world: World, thing: InstanceView) -> str | None:
    """If *thing* has a portal, dim note that the link still holds after move."""
    dest_id = world.get_portal_to(thing.id)
    if not dest_id:
        return None
    dest = world.get_instance(dest_id)
    dname = display_name(dest.name) if dest else "bound place"
    if world.is_portal_locked(thing.id):
        how = "locked · unlock first"
    elif world.install_container_of(thing.id):
        how = "install to run"
    else:
        how = "open / enter (floor portal)"
    return fmt.hint(
        f"portal still → {dname}  ·  {how}  ·  portal clear to unbind"
    )


# Floor open/run without a device — physical door shells only.
# Apps/games (thing/app, thing/game, bare cartridges, …) must be installed
# in a bin/device (under the pillows, in the terminal, …).
_FLOOR_PORTAL_SUBTYPES: frozenset[str] = frozenset(
    {
        "door",
        "hatch",
        "gate",
        "portal",
        "shell",
        "entrance",
        "exit",
        "threshold",
    }
)


def _is_floor_portal_token(thing: InstanceView) -> bool:
    """True when this portal is a door-like shell (not an install-only app)."""
    sub = (thing.ven_subtype or "").strip().lower()
    return sub in _FLOOR_PORTAL_SUBTYPES


def _portal_floor_ready(
    world: World, thing: InstanceView
) -> InstanceView | None:
    """
    Holder for a *door-like* portal token loose on the current place floor.

    Subtypes door/hatch/gate/… open without a device.
    Apps and other portal things need install (put in box/terminal/…).
    Returns the current place as synthetic holder, or None if not floor-ready.
    """
    if not world.get_portal_to(thing.id):
        return None
    if not _is_floor_portal_token(thing):
        return None
    if world.install_container_of(thing.id) is not None:
        return None
    loc = world.player_location()
    if not loc:
        return None
    cont = world.container_of(thing.id)
    if cont and cont[0] == loc.id:
        return loc
    return None


def _open_smart(world: World, arg: str) -> CommandResult:
    """
    open <name> — portal door/token if bound, else folio reader.

    unlock / enter / run stay portal-only; open shares the English verb with books.
    """
    raw = (arg or "").strip()
    if not raw:
        return CommandResult(
            True,
            fmt.hint(
                "Usage: open <door|folio>  ·  unlock <door> [with <key>]\n"
                "  Portals: open / enter / run  ·  Books: open / read / folio open"
            ),
        )
    # Prefer portal travel when the name matches a bound portal here
    portal_hits = [
        c
        for c in world.resolve_here_candidates()
        if _names_match_thing(raw, c) and world.get_portal_to(c.id)
    ]
    if len(portal_hits) == 1:
        return _run(world, raw, verb="open")
    if len(portal_hits) > 1:
        return CommandResult(
            False, _format_ambiguous(world, raw, portal_hits)
        )
    # Folio path (existing open shorthand)
    return _book_cmd(world, f"open {raw}")


def _run(world: World, arg: str, *, verb: str = "run") -> CommandResult:
    """
    run|open|enter|activate|use <portal> [from <device>]

    Soft: if exactly one installed match, enter it.
    Apps usually need install (inside a non-place container).
    Floor portal tokens (doors, room shells) enter without install.
    Locked portals require unlock first (keys optional).
    Destination is a real place via portal bind — never a paths entry.
    """
    v = (verb or "run").lower().strip() or "run"
    raw = (arg or "").strip()
    if not raw:
        return CommandResult(
            True,
            fmt.hint(
                f"Usage: {v} <portal>  ·  run <app> from <device>\n"
                "  Apps: install in a device, then run.  "
                "Doors on the floor: open / enter.  "
                "Locked: unlock <door> [with <key>] first.  "
                "Bind: portal <thing> -> <place>"
            ),
        )
    app_q = raw
    device_q: str | None = None
    low = raw.lower()
    if " from " in low:
        idx = low.rfind(" from ")
        app_q = raw[:idx].strip()
        device_q = raw[idx + 6 :].strip() or None
    if not app_q:
        return CommandResult(
            True, fmt.hint("Usage: run <app>  ·  run <app> from <device>")
        )

    # All reachable matches by name
    candidates = [
        c
        for c in world.resolve_here_candidates()
        if _names_match_thing(app_q, c)
    ]
    if device_q:
        device_matches = [
            c
            for c in world.resolve_here_candidates()
            if _names_match_thing(device_q, c)
        ]
        if not device_matches:
            return CommandResult(
                False, fmt.err(f"No device {device_q!r} here.  Try: examine / inv")
            )
        if len(device_matches) > 1:
            return CommandResult(
                False, _format_ambiguous(world, device_q, device_matches)
            )
        device = device_matches[0]
        # App must be direct content of that device
        candidates = [
            c
            for c in world.contents(device.id)
            if _names_match_thing(app_q, c)
        ]
        if not candidates:
            return CommandResult(
                False,
                fmt.err(
                    f"No {app_q!r} installed in {device.name}.  "
                    f"put {app_q} in {device.name} first."
                ),
            )
        installed = [(c, device) for c in candidates]
    else:
        installed = []
        loose_or_floor = []
        for c in candidates:
            holder = world.install_container_of(c.id)
            if holder is not None:
                installed.append((c, holder))
            else:
                loose_or_floor.append(c)

        # Floor portal tokens (doors / room shells): no device install needed
        if not installed:
            floor_ready: list[tuple[InstanceView, InstanceView]] = []
            for c in loose_or_floor:
                place_holder = _portal_floor_ready(world, c)
                if place_holder is not None:
                    floor_ready.append((c, place_holder))
            if len(floor_ready) == 1:
                installed = floor_ready
            elif len(floor_ready) > 1:
                lines = [
                    fmt.err(f"Ambiguous portal {app_q!r}.  Be specific:"),
                ]
                for app, _h in floor_ready:
                    lines.append(fmt.hint(f"  unlock {app.name}"))
                return CommandResult(False, "\n".join(lines))

        if not installed:
            if loose_or_floor or candidates:
                has_portal = any(world.get_portal_to(c.id) for c in loose_or_floor)
                floor_door = any(
                    world.get_portal_to(c.id) and _is_floor_portal_token(c)
                    for c in loose_or_floor
                )
                if has_portal and not floor_door:
                    # App/game on floor or in inv — needs a device/box install
                    return CommandResult(
                        False,
                        fmt.err(
                            f"{app_q!r} is not installed.  "
                            f"put / install it in a box or device, then {v} "
                            f"(floor only works for door/hatch shells)."
                        ),
                    )
                if has_portal:
                    return CommandResult(
                        False,
                        fmt.err(
                            f"{app_q!r} has a portal but is not on the floor here "
                            f"and not installed.  drop it here, or put it in a device."
                        ),
                    )
                return CommandResult(
                    False,
                    fmt.err(
                        f"{app_q!r} is not installed.  "
                        f"put it in a device (terminal, bag, under the pillows…), "
                        f"then {v}."
                    ),
                )
            return CommandResult(
                False,
                fmt.err(
                    f"No {app_q!r} here to {v}.  "
                    f"examine  ·  unlock <door>  ·  put <app> in <device>"
                ),
            )
        if len(installed) > 1:
            lines = [
                fmt.err(f"Ambiguous run target {app_q!r}.  Be specific:"),
            ]
            for app, holder in installed:
                lines.append(
                    fmt.hint(f"  run {app.name} from {holder.name}")
                )
            return CommandResult(False, "\n".join(lines))

    app, holder = installed[0]
    dest_id = world.get_portal_to(app.id)
    if not dest_id:
        return CommandResult(
            False,
            fmt.err(
                f"{display_name(app.name)} has no world bound.  "
                f"portal {app.name} -> <place>"
            ),
        )
    dest = world.get_instance(dest_id)
    if dest is None or dest.ven_kind != "place":
        return CommandResult(
            False,
            fmt.err(
                f"Portal on {display_name(app.name)} is broken "
                f"(missing place).  portal clear {app.name}"
            ),
        )

    if world.is_portal_locked(app.id):
        return _portal_locked_refusal(world, app, verb=v)

    # Remember where we stood (and which install) so logout is not a room exit
    origin = world.player_location()
    if not origin:
        return CommandResult(True, fmt.hint("Nowhere."))
    if origin.id == dest.id:
        return CommandResult(
            False,
            fmt.err(f"Already in {display_name(dest.name)}."),
        )

    world.push_portal_session(
        return_place_id=origin.id,
        app_id=app.id,
        app_name=app.name or "",
        device_id=holder.id,
        device_name=holder.name or "",
        dest_place_id=dest.id,
        dest_name=dest.name or "",
    )
    world.move_player(dest.id)
    sub = format_kind_label("place", dest.ven_subtype) if dest.ven_subtype else "place"
    floor_mode = holder.ven_kind == "place"
    if floor_mode:
        travel = fmt.hint(
            f"{v} {display_name(app.name)}  →  "
            f"{display_name(dest.name)}  ({sub})"
        )
    else:
        travel = fmt.hint(
            f"{v} {display_name(app.name)} from {display_name(holder.name)}  →  "
            f"{display_name(dest.name)}  ({sub})"
        )
    leave = fmt.hint("logout  ·  return to where you entered from (not a room exit)")
    return CommandResult(
        True,
        fmt.join_blocks(travel, leave, _look(world), gap=1),
        clear_log=True,
    )


def _logout(world: World, arg: str) -> CommandResult:
    """
    Leave the current run session: return to the place you ran from.

    Not the same as following a reverse link — works even if you wandered
    inside the app world. Nested runs pop one frame at a time.
    """
    _ = arg  # reserved (e.g. logout all later)
    frame = world.peek_portal_session()
    if frame is None:
        return CommandResult(
            True,
            fmt.hint(
                "Nothing to log out of.  "
                "logout only ends a run session (portal travel)."
            ),
        )
    popped = world.pop_portal_session()
    assert popped is not None
    ret_id = str(popped.get("return_place_id") or "").strip()
    ret = world.get_instance(ret_id) if ret_id else None
    if ret is None or ret.ven_kind != "place":
        return CommandResult(
            False,
            fmt.err(
                "Logout failed — return place is gone.  "
                "You're still wherever you are; session cleared."
            ),
        )

    app_name = display_name(str(popped.get("app_name") or "app"))
    device_name = display_name(str(popped.get("device_name") or ""))
    world.move_player(ret.id)
    if device_name:
        travel = fmt.hint(
            f"logout · {app_name}  →  {display_name(ret.name)}  "
            f"(via {device_name})"
        )
    else:
        travel = fmt.hint(f"logout · {app_name}  →  {display_name(ret.name)}")
    deeper = world.peek_portal_session()
    extra = None
    if deeper is not None:
        dname = display_name(str(deeper.get("dest_name") or "another world"))
        extra = fmt.hint(f"still in session · {dname}  ·  logout again to leave")
    return CommandResult(
        True,
        fmt.join_blocks(travel, extra, _look(world), gap=1),
        clear_log=True,
    )


def _inv(world: World, arg: str = "") -> str:
    """
    Carried items in the same placement language as look.

    - No bins: one **Inventory** grid (prime · name · code).
    - Bins present: **Carrying** (loose) + each bin as a look-style bucket
      with its contents listed underneath (empty bins still show).
    - ``inv --deep`` / ``inv deep``: nested bins under carried bins open one
      layer (same as look --deep).
    """
    from .wiki import parse_deep_flag

    _rest, deep = parse_deep_flag(arg or "")
    player = _player_instance(world)
    if not player:
        return fmt.hint("No player set.")
    items = world.inventory()
    if not items:
        return fmt.hint("You carry nothing.")

    has_bin = any(_is_placement_bin(it) for it in items)
    if has_bin:
        sections = _placement_sections(
            world,
            player.id,
            kids=items,
            loose_label="Carrying",
        )
        blocks = _format_look_presence_blocks(
            sections, world=world, deep=deep
        )
        tip = (
            "examine <box>  ·  take <thing> from <box>  ·  put <thing> in <box>"
        )
        if not deep:
            tip += "  ·  inv --deep"
        return fmt.join_blocks(
            fmt.section("Inventory"),
            *blocks,
            fmt.hint(tip),
            gap=1,
        )

    # Flat carry — same columns as look, single section
    blocks = _format_look_presence_blocks(
        [(fmt.section("Inventory"), items, False)],
        world=world,
        deep=deep,
    )
    tip = "take / drop  ·  put in a bin to group"
    if not deep and any(_is_placement_bin(it) for it in items):
        tip += "  ·  inv --deep"
    return fmt.join_blocks(*blocks, fmt.hint(tip), gap=1)


def _record_move_history(
    world: World,
    thing: InstanceView,
    *,
    verb: str,
    story_when: str,
    node_index: int | None,
    note: str,
    also: InstanceView | None = None,
    also_verb: str = "receive",
    also_note: str = "",
    extra_legs: list[tuple[InstanceView, str, str]] | None = None,
) -> str:
    """
    Movement history: always on the moved instance; optional vessel / place /
    player legs. All legs share one event_code (HST-NNN).

    Returns the shared event_code.
    """
    from .story_when import resolve_history_where

    where = resolve_history_where(world)
    place_id = where["place_instance_id"]
    place_name = where["place_name"] or ""
    realm_id = where["realm_instance_id"]
    realm_name = where["realm_name"] or ""
    tl_id = where["timeline_instance_id"]
    tl_name = where["timeline_name"] or ""

    legs: list[dict] = [
        {
            "subject_type": "instance",
            "subject_id": thing.id,
            "verb": verb,
            "note": note,
        }
    ]
    seen: set[str] = {thing.id}

    def _add_leg(inst: InstanceView | None, v: str, n: str) -> None:
        if inst is None or inst.id in seen:
            return
        seen.add(inst.id)
        legs.append(
            {
                "subject_type": "instance",
                "subject_id": inst.id,
                "verb": v,
                "note": n,
            }
        )

    if also is not None:
        _add_leg(also, also_verb, also_note or note)
    for inst, v, n in extra_legs or []:
        _add_leg(inst, v, n)

    return world.record_history_event(
        legs,
        story_when=story_when,
        node_index=node_index,
        place_instance_id=place_id,
        place_name=place_name,
        realm_instance_id=realm_id,
        realm_name=realm_name,
        timeline_instance_id=tl_id,
        timeline_name=tl_name,
    )


def _player_instance(world: World) -> InstanceView | None:
    pid = world.player_id()
    if not pid:
        return None
    return world.get_instance(pid)


def _take(world: World, arg: str) -> str:
    """
    take <thing>                 — from the place floor
    take <thing> from <box>      — out of a reachable container (room or inventory)
    get …                        — same as take
    Optional story when: when @N  ·  --when 0  (default @unknown)
    """
    from .story_when import peel_when_anywhere

    if not arg:
        return fmt.hint(
            "Take what?  take <thing>  |  take <thing> from <box>  "
            "[when @N | --when 0]"
        )

    arg, story_when, node_index = peel_when_anywhere(arg)

    # take X from Y
    lower = arg.lower()
    if " from " in lower:
        idx = lower.rfind(" from ")
        thing_name = arg[:idx].strip()
        cont_name = arg[idx + 6 :].strip()
        if not thing_name or not cont_name:
            return fmt.hint("Usage: take <thing> from <container>")
        cont = world.resolve_here_named(cont_name)
        if not cont:
            return fmt.err(
                f"No container {cont_name!r} here or in inventory.  "
                f"Try: inv  ·  examine <name>"
            )
        if not world.is_reachable(cont.id):
            return fmt.err(f"{cont.name} is not within reach.")
        thing = world.find_in_container(cont.id, thing_name)
        if not thing:
            # list what's inside for a helpful error
            inside = world.contents(cont.id)
            if not inside:
                return fmt.err(f"{cont.name} is empty.")
            names = ", ".join(c.name for c in inside)
            return fmt.err(
                f"No {thing_name!r} in {cont.name}.  Inside: {names}"
            )
        prior = world.container_of(thing.id)
        world.take_from(thing.id, cont.id)
        _push_put_undo(world, thing.id, prior, f"take {thing.name}")
        player = _player_instance(world)
        tname = display_name(thing.name)
        cname = display_name(cont.name)
        code = _record_move_history(
            world,
            thing,
            verb="take",
            story_when=story_when,
            node_index=node_index,
            note=f"from {cname}",
            also=cont,
            also_verb="give",
            also_note=f"gave {tname}",
            extra_legs=[
                (player, "receive", f"took {tname} from {cname}"),
            ]
            if player
            else None,
        )
        # Re-read instance (still same id; portal on state_json is unchanged)
        moved = world.get_instance(thing.id) or thing
        ok_line = (
            f"Taken · {thing.name}  from  {cont.name}  ·  "
            f"story {story_when}  ·  {code}"
        )
        portal_h = _portal_binding_hint(world, moved)
        if portal_h:
            return fmt.join_blocks(fmt.ok(ok_line), portal_h, gap=0)
        return fmt.ok(ok_line)

    # take from floor
    thing = world.resolve_here_named(arg)
    if not thing:
        return fmt.err(
            f"You don't see {arg!r} here.  "
            f"If it's in a box: take {arg} from <box>"
        )
    loc = world.player_location()
    cont = world.container_of(thing.id)
    if not loc or not cont or cont[0] != loc.id:
        # Maybe it's nested in something they're carrying — hint
        if cont:
            holder = world.get_instance(cont[0])
            hname = holder.name if holder else "something"
            return fmt.err(
                f"{thing.name} is inside {hname}.  "
                f"Try: take {thing.name} from {hname}"
            )
        return fmt.err(f"{thing.name} is not on the ground here.")
    if not world.takeable(thing):
        return fmt.err(
            f"Cannot take a {thing.ven_kind} ({thing.name}).  "
            f"Bins and things: dig bin <name> or create+spawn.  "
            f"Places stay free-standing (go/link), not in inventory."
        )
    prior = cont
    try:
        world.take(thing.id)
    except ValueError as e:
        return fmt.err(str(e))
    _push_put_undo(world, thing.id, prior, f"take {thing.name}")
    player = _player_instance(world)
    tname = display_name(thing.name)
    pname = display_name(loc.name) if loc else "here"
    code = _record_move_history(
        world,
        thing,
        verb="take",
        story_when=story_when,
        node_index=node_index,
        note=f"from floor {pname}",
        also=loc,
        also_verb="give",
        also_note=f"gave {tname} from floor",
        extra_legs=[
            (player, "receive", f"took {tname} from floor"),
        ]
        if player
        else None,
    )
    return fmt.ok(
        f"Taken · {thing.name}  ·  story {story_when}  ·  {code}"
    )


def _drop(world: World, arg: str) -> str:
    from .ids import names_match
    from .story_when import peel_when_anywhere

    if not arg:
        return fmt.hint("Drop what?  drop <thing> [when @N | --when 0]")
    arg, story_when, node_index = peel_when_anywhere(arg)
    # drop only top-level inventory (not nested — take from first)
    for it in world.inventory():
        if names_match(arg, it.name):
            prior = world.container_of(it.id)
            world.drop(it.id)
            _push_put_undo(world, it.id, prior, f"drop {it.name}")
            loc = world.player_location()
            player = _player_instance(world)
            tname = display_name(it.name)
            pname = display_name(loc.name) if loc else "here"
            code = _record_move_history(
                world,
                it,
                verb="drop",
                story_when=story_when,
                node_index=node_index,
                note=f"to floor {pname}",
                also=loc,
                also_verb="receive",
                also_note=f"received {tname} on floor",
                extra_legs=[
                    (player, "give", f"dropped {tname}"),
                ]
                if player
                else None,
            )
            return fmt.ok(
                f"Dropped · {it.name}  ·  story {story_when}  ·  {code}"
            )
    return fmt.err(f"You aren't carrying {arg!r}.")


def _push_put_undo(
    world: World,
    item_id: str,
    prior: tuple[str, str] | None,
    summary: str,
) -> None:
    """Undo a put_in/take/drop by restoring previous container+slot (or deleting containment)."""

    def apply(w: World) -> None:
        if prior is None:
            w.conn.execute(
                "DELETE FROM containment WHERE contained_instance_id = ?",
                (item_id,),
            )
            w.conn.commit()
        else:
            w.put_in(item_id, prior[0], slot=prior[1])

    world.undo_stack.push(summary, apply)


def _push_book_page_body_undo(
    world: World,
    page_id: str,
    prior_body: str,
    summary: str,
) -> None:
    """Undo a line-level page body edit by restoring the prior body text."""

    def apply(w: World) -> None:
        w.conn.execute(
            "UPDATE book_pages SET body = ? WHERE id = ?",
            (prior_body, page_id),
        )
        w.conn.commit()

    world.undo_stack.push(summary, apply)


def _push_book_page_title_body_undo(
    world: World,
    page_id: str,
    prior_title: str,
    prior_body: str,
    summary: str,
) -> None:
    """Undo a single-page editor save that changed title and/or body together."""

    def apply(w: World) -> None:
        w.conn.execute(
            "UPDATE book_pages SET title = ?, body = ? WHERE id = ?",
            (prior_title, prior_body, page_id),
        )
        w.conn.commit()

    world.undo_stack.push(summary, apply)


def _push_book_page_title_undo(
    world: World,
    page_id: str,
    prior_title: str,
    summary: str,
) -> None:
    """Undo a page-title change only."""

    def apply(w: World) -> None:
        w.conn.execute(
            "UPDATE book_pages SET title = ? WHERE id = ?",
            (prior_title, page_id),
        )
        w.conn.commit()

    world.undo_stack.push(summary, apply)


def _push_book_page_delete_undo(
    world: World,
    book_instance_id: str,
    page_id: str,
    summary: str,
) -> None:
    """Undo page add/insert by deleting the created page and renumbering."""

    def apply(w: World) -> None:
        w.delete_book_page(book_instance_id, page_id)

    world.undo_stack.push(summary, apply)


def _examine(world: World, arg: str, *, deep: bool | None = None) -> str:
    """
    examine <thing>           — detail; lore count hint
    examine --deep <thing>    — same + full lore bodies (+ deeper compose)
    in deep at <thing>        — aliases: exam, inspect, in
    """
    from .wiki import parse_deep_flag

    if deep is None:
        arg, deep = parse_deep_flag(arg)
    else:
        # Already peeled by look; still strip a redundant deep token if present
        arg, deep2 = parse_deep_flag(arg)
        deep = deep or deep2
    arg = _peel_look_target(arg)

    if not arg:
        return fmt.hint(
            "Examine what?  examine <thing>  ·  examine realm  ·  examine timeline\n"
            "  Full lore:  examine --deep <thing>  ·  in deep at <thing>\n"
            "  Also: look at door  ·  look in drawer  ·  look on table"
        )
    thing, err = _resolve_instance_target(world, arg)
    if err or thing is None:
        return err or fmt.err(f"No match for {arg!r}.")
    assert thing is not None
    ref = world.short_ref_of(thing.id)
    # title → kind | realm | timeline  (ids go to footer)
    header = fmt.title_line(thing.name, kind=thing.ven_kind)
    context = _instance_context_line(world, thing)
    head = fmt.join_blocks(header, context, gap=0)
    body = fmt.prose(thing.description)
    tdf_meta = None
    if world.is_tdf(thing.id):
        payload = world.tdf_payload(thing.id) or {}
        data = payload.get("data") or {}
        code = payload.get("code") or "?"
        sub = payload.get("subtype") or ""
        k = payload.get("kind") or ""
        start = (data.get("start") or "").strip()
        end = (data.get("end") or "").strip()
        if start and end:
            data_line = f"{start} → {end}"
        else:
            data_line = (data.get("raw") or data.get("when") or "").strip()
        tdf_meta = fmt.hint(
            f"TDF {code}  ·  ticket/{sub or '—'}  ·  kind {k or '—'}"
            + (f"  ·  {data_line}" if data_line else "")
        )
    book_meta = None
    if _is_folio_kind(thing.ven_kind):
        from .book import format_status_markup

        n = len(world.list_book_pages(thing.id))
        status = world.book_status(thing.id)
        # Status color tags must not pass through fmt.hint (which escapes markup)
        book_meta = (
            f"[dim]{n} leaf/page(s)  ·  [/dim]{format_status_markup(status)}"
            f"[dim]  ·  folio open {fmt.safe(thing.name)}#{fmt.safe(ref)}[/dim]"
        )

    # Placement: Here = loose inside this instance; each nested bin is
    # an opened bucket (first-level kids). --deep expands those kids one more
    # layer when they are bins. Empty nested bins still show.
    placement = _placement_sections(world, thing.id)
    placement_blocks = _format_look_presence_blocks(
        placement, world=world, deep=deep
    )
    run_hint_line = None
    if _placement_has_runnable(world, placement, deep=deep):
        run_hint_line = fmt.hint(
            f"run <app> from {thing.name}  ·  portals stay off paths"
        )

    portal_meta = None
    portal_dest_id = world.get_portal_to(thing.id)
    if portal_dest_id:
        pdest = world.get_instance(portal_dest_id)
        pname = pdest.name if pdest else "?"
        holder = world.install_container_of(thing.id)
        locked = world.is_portal_locked(thing.id)
        lock_bit = "locked · " if locked else ""
        if locked:
            run_hint = f"unlock {thing.name} [with <key>] · then open"
        elif holder:
            run_hint = f"run {thing.name} from {holder.name}"
        elif _portal_floor_ready(world, thing):
            run_hint = f"open / enter {thing.name}"
        elif _is_floor_portal_token(thing):
            run_hint = "drop here to open, or install then run"
        else:
            run_hint = "install in a box/device, then run"
        portal_meta = fmt.hint(f"portal → {pname}  ·  {lock_bit}{run_hint}")
    lineage_block = _format_lineage_section(world, thing.ven_id)
    compose_block = _format_compose_section(world, thing.ven_id, deep=deep)

    dialog_meta = None
    if thing.ven_kind == "person":
        last = world.last_dialog_for_person(thing.id)
        if last is not None:
            teaser = dialog_teaser_line(
                title=last["title"],
                when_label=last["when_label"],
                transcript=last["transcript"],
            )
            dialog_meta = fmt.hint(f"last dialog · {teaser}")

    lore_rows = list(world.lore_for("instance", thing.id))
    lore_rows += list(world.lore_for("ven", thing.ven_id))
    lore_block = None
    if deep:
        if lore_rows:
            lore_block = _format_lore_rows(f"Lore · {thing.name}", lore_rows)
        else:
            lore_block = fmt.hint("No related lore revisions.")
    elif lore_rows:
        lore_block = fmt.hint(
            f"{len(lore_rows)} related lore revision(s)  ·  examine --deep {thing.name}"
        )

    # Technical ids last — not between context and prose
    id_footer = fmt.hint(
        f"#{ref}  ·  instance {thing.id}  ·  ven {thing.ven_slug} ({thing.ven_id})"
    )

    return fmt.join_blocks(
        head,
        body,
        tdf_meta,
        book_meta,
        portal_meta,
        lineage_block,
        compose_block,
        *placement_blocks,
        run_hint_line,
        dialog_meta,
        lore_block,
        id_footer,
        gap=1,
    )


def _format_lineage_section(world: World, ven_id: str) -> str | None:
    path = world.lineage_path(ven_id)
    if len(path) < 2:
        return None
    labels = [display_name(v.name) for v in path]
    lines = [
        fmt.section("Lineage"),
        fmt.hint(" › ".join(labels)),
    ]
    return "\n".join(lines)


def _format_compose_section(
    world: World, ven_id: str, *, deep: bool = False
) -> str | None:
    from .wiki import composition_depth_for_deep, format_composition_tree_lines

    tree = world.composition_tree(
        ven_id, max_depth=composition_depth_for_deep(deep)
    )
    if not tree:
        return None
    title = "Composed of" + (" (deep)" if deep else "")
    lines = [fmt.section(title)]
    lines.extend(format_composition_tree_lines(tree))
    return "\n".join(lines)


def _person_inner_summary(world: World, person_id: str) -> str:
    """
    Short who-list summary: instance name · VEN · type [+ subtype].
    """
    inner = world.contents(person_id)
    kinds = person_inner_kinds()
    bits: list[str] = []
    for c in inner:
        if is_inner_life_kind(c.ven_kind, c.ven_subtype):
            inst = display_name(c.name)
            ven = display_name(c.ven_name)
            sub = (c.ven_subtype or "").strip()
            if sub:
                bits.append(f"{inst} · {ven} ({c.ven_kind}/{sub})")
            else:
                bits.append(f"{inst} · {ven} ({c.ven_kind})")
    return " · ".join(bits)


def _who(world: World) -> str:
    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")
    people = [c for c in world.contents(loc.id) if c.ven_kind == "person"]
    if not people:
        return fmt.hint("No one here.")
    lines = [fmt.section("Here")]
    for p in people:
        lines.append(fmt.bullet(p.name, kind="person"))
        inner = _person_inner_summary(world, p.id)
        if inner:
            lines.append(f"      [dim]{fmt.safe(inner)}[/dim]")
        last = world.last_dialog_for_person(p.id)
        if last is not None:
            teaser = dialog_teaser_line(
                title=last["title"],
                when_label=last["when_label"],
                transcript=last["transcript"],
            )
            lines.append(f"      [dim]last dialog · {fmt.safe(teaser)}[/dim]")
    return "\n".join(lines)


def _wiki(world: World, arg: str) -> CommandResult:
    """
    wiki [<label>] [deep]
    wiki link <from> <to>
    wiki unlink <from> <to>

    Dossier for a real VEN or instance (not a book page editor).
    Notes = lore. Sub-links = meta wiki_links (ven ids only).
    Trailing ``deep`` expands nested composition.
    TUI opens the soft reader (same frame as folio); message is the full dossier
    for REPL / print path.
    """
    from .wiki import format_wiki_dossier, parse_deep_flag, resolve_wiki_target

    arg = arg.strip()
    if not arg:
        # default: place you're standing (its prime VEN)
        loc = world.player_location()
        if not loc:
            return CommandResult(
                True,
                fmt.hint("Nowhere.  Usage: wiki <ven|instance name> [deep]"),
            )
        label = (loc.ven_slug or loc.name or "").strip()
        target = resolve_wiki_target(world, label)
        if target.status == "missing":
            label = loc.name
            target = resolve_wiki_target(world, label)
        body = format_wiki_dossier(world, target)
        if target.status in ("missing", "ambiguous"):
            return CommandResult(True, body)
        return CommandResult(True, body, open_wiki=(label, False))

    low = arg.lower()
    if low.startswith("link ") or low.startswith("unlink "):
        return CommandResult(True, _wiki_link_cmd(world, arg))

    label, deep = parse_deep_flag(arg)
    if not label:
        return CommandResult(
            True, fmt.hint("Usage: wiki <ven|instance name> [deep]")
        )
    target = resolve_wiki_target(world, label)
    body = format_wiki_dossier(world, target, deep=deep)
    if target.status in ("missing", "ambiguous"):
        return CommandResult(True, body)
    return CommandResult(True, body, open_wiki=(label, deep))


def _wiki_link_cmd(world: World, arg: str) -> str:
    """wiki link <from> <to>  ·  wiki unlink <from> <to>"""
    from .wiki import resolve_wiki_target

    parts = arg.split(maxsplit=1)
    if len(parts) < 2:
        return fmt.hint("Usage: wiki link <from> <to>  ·  wiki unlink <from> <to>")
    action = parts[0].lower()
    rest = parts[1].strip()
    tokens = rest.split()
    if len(tokens) < 2:
        return fmt.hint(
            "Usage: wiki link <from> <to>  ·  both ends must be real VENs/instances"
        )

    ta = tb = None
    for i in range(len(tokens) - 1, 0, -1):
        left = " ".join(tokens[:i])
        right = " ".join(tokens[i:])
        cand_a = resolve_wiki_target(world, left)
        cand_b = resolve_wiki_target(world, right)
        if cand_a.status in ("ven", "instance") and cand_b.status in (
            "ven",
            "instance",
        ):
            ta, tb = cand_a, cand_b
            break
    if ta is None or tb is None:
        return fmt.err(
            "Could not split into two resolvable targets.  "
            "Use unique prime names or instance names."
        )

    from_ven = ta.ven or (
        world.get_ven(ta.instance.ven_id) if ta.instance is not None else None
    )
    to_ven = tb.ven or (
        world.get_ven(tb.instance.ven_id) if tb.instance is not None else None
    )
    if from_ven is None or to_ven is None:
        return fmt.err("Could not resolve primes for both ends.")

    if action == "unlink":
        try:
            removed = world.remove_wiki_link(from_ven.id, to_ven.id)
        except ValueError as e:
            return fmt.err(str(e))
        if not removed:
            return fmt.hint(
                f"No sub-link from {display_name(from_ven.name)} "
                f"to {display_name(to_ven.name)}."
            )
        return fmt.ok(
            f"Wiki unlink · {display_name(from_ven.name)} ↛ "
            f"{display_name(to_ven.name)}"
        )

    try:
        world.add_wiki_link(from_ven.id, to_ven.id)
    except ValueError as e:
        return fmt.err(str(e))
    return fmt.ok(
        f"Wiki link · {display_name(from_ven.name)} → {display_name(to_ven.name)}  "
        f"(wiki {from_ven.slug})"
    )


def _talk(world: World, arg: str) -> str:
    """Start a back-and-forth dialog with a person here. End with /fin."""
    if world.active_dialog is not None:
        return fmt.hint("Already in a dialog — finish with /fin first.")
    try:
        person_q, title, when_label = parse_talk_args(arg)
    except ValueError as e:
        return fmt.hint(str(e))

    partner, err = _resolve_one(world, person_q, kind="person")
    if err:
        return err
    assert partner is not None
    pid = world.player_id()
    if not pid:
        return fmt.hint("No player avatar set.")
    if partner.id == pid:
        return fmt.err("You cannot talk to yourself that way.")
    player = world.get_instance(pid)
    if player is None:
        return fmt.hint("No player avatar.")
    loc = world.player_location()

    session = DialogSession(
        partner_id=partner.id,
        partner_name=display_name(partner.name),
        player_id=pid,
        player_name=display_name(player.name),
        place_id=loc.id if loc else None,
        timeline_id=loc.timeline_instance_id if loc else None,
        title=title,
        when_label=when_label,
    )
    world.active_dialog = session
    stamp = when_label or "—"
    ttl = session.display_title()
    return fmt.join_blocks(
        fmt.ok(f"Talking with {session.partner_name}"),
        fmt.hint(f"title {ttl}  ·  when {stamp}"),
        fmt.hint(
            "Lines alternate You → them.  /you …  /them …  force a speaker.  "
            f"/when <stamp> sets when  ·  {FIN_TOKEN} ends the dialog."
        ),
        gap=0,
    )


def _dialog_input(world: World, line: str) -> str:
    sess: DialogSession = world.active_dialog
    assert sess is not None
    stripped = line.strip()
    low = stripped.lower()
    if low == FIN_TOKEN or stripped == FIN_TOKEN:
        return _finish_dialog(world)
    if low.startswith("/when"):
        try:
            new_when = parse_dialog_when_line(stripped)
        except ValueError as e:
            return fmt.hint(str(e))
        sess.when_label = new_when
        stamp = new_when or "—"
        return fmt.join_blocks(
            fmt.ok("When stamp updated"),
            fmt.hint(f"when {stamp}  ·  title {sess.display_title()}"),
            fmt.hint(f"… continue, or {FIN_TOKEN}"),
            gap=0,
        )
    try:
        speaker, text = sess.append_line(line)
    except ValueError as e:
        return fmt.hint(str(e))
    who = "you" if speaker == sess.player_name else None
    return fmt.join_blocks(
        format_script_turn(speaker, text, you_label=who),
        fmt.hint(f"… continue, or {FIN_TOKEN}"),
        gap=0,
    )


def _finish_dialog(world: World) -> str:
    sess: DialogSession | None = world.active_dialog
    if sess is None:
        return fmt.hint("No active dialog.")
    world.active_dialog = None

    if not sess.turns:
        return fmt.hint("Dialog cancelled (no turns spoken).")

    transcript = sess.transcript_text()
    title = sess.display_title()
    did = world.save_dialog(
        title=title,
        when_label=sess.when_label,
        place_instance_id=sess.place_id,
        timeline_instance_id=sess.timeline_id,
        speaker_a_id=sess.player_id,
        speaker_b_id=sess.partner_id,
        speaker_a_name=sess.player_name,
        speaker_b_name=sess.partner_name,
        transcript=transcript,
    )
    row = world.get_dialog(did)
    dslug = world.dialog_slug_of(row) if row else did

    # Lore note: dialog took place between the two characters
    lore_title = f"Dialog · {title}"
    lore_body = (
        f"A dialog took place between {sess.player_name} and {sess.partner_name}.\n"
        f"Transcript id: {did}\n"
        f"Transcript: {dslug}\n"
        f"Re-read: dialogs show {dslug}"
    )
    if sess.place_id:
        world.add_lore(
            "instance",
            sess.place_id,
            body=lore_body,
            title=lore_title,
            timeline_instance_id=sess.timeline_id,
            when_label=sess.when_label,
            author="dialog",
        )
    world.add_lore(
        "instance",
        sess.partner_id,
        body=lore_body,
        title=lore_title,
        timeline_instance_id=sess.timeline_id,
        when_label=sess.when_label,
        author="dialog",
    )

    return fmt.join_blocks(
        fmt.ok(f"Dialog ended · {title}"),
        fmt.hint(
            f"saved {dslug}  ·  lore noted for {sess.player_name} & {sess.partner_name}"
        ),
        fmt.hint(
            f"Re-read:  dialogs  ·  dialogs show {dslug}  ·  dialogs show 1"
        ),
        gap=0,
    )


def _dialog_place_id(world: World) -> str | None:
    loc = world.player_location()
    return loc.id if loc else None


def _format_dialogs_list(
    world: World,
    rows: list,
    *,
    scope: str,
) -> str:
    """Render a numbered dialog list (place-scoped or all)."""
    if not rows:
        if scope == "here":
            return fmt.hint(
                "No dialogs in this place.  "
                "talk <person> … /fin  ·  dialogs all  for every transcript"
            )
        return fmt.hint("No completed dialogs yet.  talk <person> … /fin")
    if scope == "here":
        loc = world.player_location()
        where = display_name(loc.name) if loc else "here"
        lines = [fmt.section(f"Dialogs · {where}")]
    else:
        lines = [fmt.section("Dialogs · all")]
    for i, r in enumerate(rows, start=1):
        stamp = r["when_label"] or "—"
        handle = world.dialog_slug_of(r)
        lines.append(
            fmt.bullet(
                f"{i}. {r['title'] or 'Untitled'}",
                f"{r['speaker_a_name']} & {r['speaker_b_name']}  ·  "
                f"when {stamp}  ·  {handle}",
            )
        )
    if scope == "here":
        lines.append(
            fmt.hint(
                "dialogs show <n|slug|title>  ·  "
                "dialogs all  ·  dialogs rename …  ·  dialogs when …"
            )
        )
    else:
        lines.append(
            fmt.hint(
                "dialogs show <n|slug|title>  ·  "
                "bare dialogs = this place only"
            )
        )
    return "\n".join(lines)


def _dialogs(world: World, arg: str) -> str:
    """List or show completed dialog transcripts; replace when-stamp."""
    arg = arg.strip()
    sub, _, rest = arg.partition(" ")
    sub = sub.lower()
    rest = rest.strip()
    place_id = _dialog_place_id(world)

    # Bare dialogs → this location only
    if not arg or sub in ("here", "local"):
        rows = world.list_dialogs(place_instance_id=place_id) if place_id else []
        if not place_id:
            return fmt.hint("Nowhere.  dialogs all  lists every transcript.")
        return _format_dialogs_list(world, rows, scope="here")

    # Global list: dialogs all | list | ls | show list
    if sub in ("all", "list", "ls", "everywhere", "global"):
        return _format_dialogs_list(
            world, world.list_dialogs(), scope="all"
        )
    if sub in ("show", "read", "open", "view") and rest.lower() in (
        "list",
        "all",
        "ls",
        "everywhere",
        "global",
    ):
        return _format_dialogs_list(
            world, world.list_dialogs(), scope="all"
        )

    if sub in ("show", "read", "open", "view"):
        if not rest:
            return fmt.hint(
                "Usage: dialogs show <number|slug|title>  ·  "
                "dialogs show list  (all places)"
            )
        row = world.find_dialog(rest, place_instance_id=place_id)
        if row is None:
            return fmt.err(
                f"No dialog matching {rest!r}.  Try: dialogs  ·  dialogs all"
            )
        return format_transcript_view(
            title=row["title"] or "Untitled dialog",
            when_label=row["when_label"],
            speaker_a=row["speaker_a_name"] or "",
            speaker_b=row["speaker_b_name"] or "",
            transcript=row["transcript"] or "",
            created_at=row["created_at"] or "",
            dialog_id=row["id"],
            dialog_slug=world.dialog_slug_of(row),
        )

    if sub in ("when", "stamp"):
        return _dialogs_set_when(world, rest)

    if sub in ("rename", "title", "call"):
        return _dialogs_rename(world, rest)

    # bare number or slug as shortcut: dialogs 1 / dialogs FIRST-MEETING
    row = world.find_dialog(arg, place_instance_id=place_id)
    if row is not None:
        return _dialogs(world, f"show {arg}")

    return fmt.hint(
        "Usage: dialogs  (this place)  ·  dialogs all  ·  "
        "dialogs show list  ·  dialogs show <n|slug|title>  ·  "
        "dialogs rename …  ·  dialogs when …"
    )


def _dialogs_set_when(world: World, rest: str) -> str:
    """
    dialogs when <n|slug|title> | when <stamp>
    dialogs when <n|slug|title> | @stamp
    dialogs when <n|slug|title> <stamp…>
    """
    rest = rest.strip()
    if not rest:
        return fmt.hint(
            "Usage: dialogs when <n|slug|title> | when <stamp>  "
            "·  dialogs when 1 | @2024-06-15"
        )
    query: str
    stamp_raw: str
    if "|" in rest:
        left, _, right = rest.partition("|")
        query = left.strip()
        stamp_raw = right.strip()
    else:
        # Last resort: first token is dialog ref if digit/id, rest is stamp
        tokens = rest.split(maxsplit=1)
        if len(tokens) < 2:
            return fmt.hint(
                "Usage: dialogs when <n|slug|title> | when <stamp>"
            )
        query, stamp_raw = tokens[0], tokens[1]

    row = world.find_dialog(query, place_instance_id=_dialog_place_id(world))
    if row is None:
        # title may be multi-word before | — already handled; try full left without |
        return fmt.err(f"No dialog matching {query!r}.  Try: dialogs  ·  dialogs all")
    try:
        new_when = parse_when_stamp(stamp_raw)
    except ValueError as e:
        return fmt.hint(str(e))
    prior = row["when_label"]
    did = row["id"]
    updated = world.set_dialog_when(did, new_when)

    def undo(w: World, dialog_id: str = did, old=prior) -> None:
        w.set_dialog_when(dialog_id, old)

    world.undo_stack.push(f"dialogs when {did}", undo)
    stamp = updated["when_label"] or "—"
    dslug = world.dialog_slug_of(updated)
    return fmt.join_blocks(
        fmt.ok(f"When stamp updated · {updated['title'] or 'Untitled'}"),
        fmt.hint(f"when {stamp}  ·  {dslug}"),
        gap=0,
    )


def _dialogs_rename(world: World, rest: str) -> str:
    """
    dialogs rename <n|slug|title> as|-> <new title>
    dialogs title <n|id|title> as|-> <new title>
    """
    rest = rest.strip()
    split = split_as_title(rest)
    if not split:
        return fmt.hint(
            "Usage: dialogs rename <n|slug|title> as <new title>  "
            "·  dialogs rename 1 -> Better Title"
        )
    query, new_title = split
    row = world.find_dialog(query, place_instance_id=_dialog_place_id(world))
    if row is None:
        return fmt.err(f"No dialog matching {query!r}.  Try: dialogs  ·  dialogs all")
    prior = row["title"] or ""
    did = row["id"]
    try:
        updated = world.set_dialog_title(did, new_title)
    except ValueError as e:
        return fmt.hint(str(e))

    def undo(w: World, dialog_id: str = did, old: str = prior) -> None:
        w.set_dialog_title(dialog_id, old, allow_empty=True)

    world.undo_stack.push(f"dialogs rename {did}", undo)
    dslug = world.dialog_slug_of(updated)
    return fmt.join_blocks(
        fmt.ok(
            f"Renamed dialog · {prior or 'Untitled'} → {updated['title']}"
        ),
        fmt.hint(f"{dslug}  ·  dialogs show {dslug}"),
        gap=0,
    )


def _help(arg: str) -> str:
    term = arg.strip()
    if not term:
        return render_help_index()
    return render_help_topic(term)


def _candidate_detail(
    world: World,
    c: InstanceView,
    *,
    include_ref: bool = True,
) -> str:
    """
    Second line under an instance name.

    When the first line already has ``Name #REF`` (include_ref=False), skip the
    repeated code so the detail is only place · kind · folio meta.
    """
    where = world.where_label(c.id)
    kind_lbl = format_kind_label(c.ven_kind, c.ven_subtype)
    bits: list[str] = []
    if include_ref:
        bits.append(f"#{world.short_ref_of(c.id)}")
    bits.extend([where, kind_lbl])
    if _is_folio_kind(c.ven_kind):
        n = len(world.list_book_pages(c.id))
        status = world.book_status(c.id) or ""
        bits.append(f"{n} leaf/page(s)")
        if status:
            bits.append(str(status))
    return " · ".join(bits)


def _format_ambiguous(world: World, query: str, matches: list[InstanceView]) -> str:
    lines = [
        fmt.err(f"Ambiguous {query!r} — {len(matches)} matches."),
        fmt.hint(
            "Qualify with: here · inv · from <box> · #FOL-001-0001  "
            "e.g. field-notes inv  ·  notes from pouch  ·  field-notes#0002"
        ),
    ]
    for c in matches:
        lines.append(
            fmt.stacked_item(
                fmt.named_ref(c.name, world.short_ref_of(c.id)),
                _candidate_detail(world, c, include_ref=False),
                kind=c.ven_kind,
            )
        )
    return "\n".join(lines)


def _resolve_one(
    world: World,
    name: str,
    *,
    kind: str | None = None,
) -> tuple[InstanceView | None, str | None]:
    """Resolve a reachable instance (place, inv, or nested in a container)."""
    matches = world.resolve_here_matches(name, kind=kind)
    if not matches:
        return None, fmt.err(
            f"No {name!r} here, in inventory, or inside a reachable container."
        )
    if len(matches) > 1:
        return None, _format_ambiguous(world, name, matches)
    inst = matches[0]
    if kind and inst.ven_kind != kind:
        return None, fmt.err(f"{inst.name} is a {inst.ven_kind}, not a {kind}.")
    return inst, None


def _split_from_container(arg: str) -> tuple[str, str] | None:
    """If *arg* ends with `` from <container>``, return (thing, container)."""
    lower = arg.lower()
    if " from " not in lower:
        return None
    idx = lower.rfind(" from ")
    thing = arg[:idx].strip()
    cont = arg[idx + 6 :].strip()
    if not thing or not cont:
        return None
    return thing, cont


def _resolve_in_container(
    world: World,
    thing_name: str,
    cont_name: str,
    *,
    kind: str | None = None,
) -> tuple[InstanceView | None, str | None]:
    """Resolve a direct content of a reachable container (take-from style)."""
    cont = world.resolve_here_named(cont_name)
    if not cont:
        return None, fmt.err(
            f"No container {cont_name!r} here or in inventory.  "
            f"Try: inv  ·  examine <name>"
        )
    if not world.is_reachable(cont.id):
        return None, fmt.err(f"{cont.name} is not within reach.")
    thing = world.find_in_container(cont.id, thing_name)
    if not thing:
        inside = world.contents(cont.id)
        if not inside:
            return None, fmt.err(f"{cont.name} is empty.")
        names = ", ".join(c.name for c in inside)
        return None, fmt.err(f"No {thing_name!r} in {cont.name}.  Inside: {names}")
    if kind and thing.ven_kind != kind:
        return None, fmt.err(f"{thing.name} is a {thing.ven_kind}, not a {kind}.")
    return thing, None


def _is_folio_kind(kind: str | None) -> bool:
    return (kind or "").lower() in ("folio", "book")


def _resolve_book_here(world: World, name: str):
    """Resolve a folio (legacy: book) here, inv, nested, or ``name from <box>``."""
    split = _split_from_container(name)
    if split:
        book_name, cont_name = split
        thing, err = _resolve_in_container(world, book_name, cont_name, kind=None)
        if err:
            return None, err
        if thing and not _is_folio_kind(thing.ven_kind):
            return None, fmt.err(f"{thing.name} is a {thing.ven_kind}, not a folio.")
        return thing, None
    # Prefer folio; accept legacy kind book
    matches = world.resolve_here_matches(name, kind="folio")
    if not matches:
        matches = world.resolve_here_matches(name, kind="book")
    if not matches:
        return None, fmt.err(f"No folio matching {name!r}.")
    if len(matches) > 1:
        return None, _format_ambiguous(world, name, matches)
    return matches[0], None


def _book_cmd(world: World, arg: str) -> CommandResult:
    """
    folio open|pages|page|leaf|line|incomplete|complete …

    ``book`` is a full alias for ``folio``. ``leaf`` is an alias for ``page``.
    """
    arg = arg.strip()
    if not arg:
        return CommandResult(
            True,
            fmt.hint(
                "Usage: folio open|pages|incomplete|complete <name>  ·  "
                "folio page add|insert|edit …  ·  "
                "(alias: book … · leaf = page)"
            ),
        )
    parts = arg.split(maxsplit=1)
    sub = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("pages", "list", "ls", "leaves"):
        if not rest:
            return CommandResult(True, fmt.hint("Usage: folio pages <name>"))
        book, err = _resolve_book_here(world, rest)
        if err:
            return CommandResult(True, err)
        assert book is not None
        return CommandResult(True, _book_pages_list(world, book))

    if sub in ("incomplete", "complete"):
        if not rest:
            return CommandResult(True, fmt.hint(f"Usage: folio {sub} <name>"))
        book, err = _resolve_book_here(world, rest)
        if err:
            return CommandResult(True, err)
        assert book is not None
        from .book import format_status_markup

        prior = world.book_incomplete(book.id)
        flag = sub == "incomplete"
        world.set_book_incomplete(book.id, flag)
        world.undo_stack.push(
            f"folio {sub} {book.name}",
            lambda w, bid=book.id, p=prior: w.set_book_incomplete(bid, p),
        )
        # Reflect resolved status (empty if still no pages). Keep color tags
        # outside fmt.ok so safe() does not escape them.
        state = world.book_status(book.id)
        return CommandResult(
            True,
            f"{fmt.ok(f'Folio · {book.name} marked')} {format_status_markup(state)}",
        )

    if sub in ("open", "read"):
        if not rest:
            return CommandResult(
                True,
                fmt.hint(
                    "Usage: folio open <name>  ·  folio open <name> from <box>  ·  "
                    "read <name>  ·  (alias: book open …)"
                ),
            )
        book, err = _resolve_book_here(world, rest)
        if err:
            return CommandResult(True, err)
        assert book is not None
        return CommandResult(
            True,
            _book_read_text(world, book, 0),
            open_book_id=book.id,
        )

    if sub in ("page", "leaf"):
        return _book_page_sub(world, rest)

    if sub == "line":
        return _book_line_sub(world, rest)

    # bare: folio <name> → open
    book, err = _resolve_book_here(world, arg)
    if book is not None:
        return CommandResult(
            True,
            _book_read_text(world, book, 0),
            open_book_id=book.id,
        )
    return CommandResult(
        True,
        fmt.hint(
            "Usage: folio open|pages|incomplete|complete <name>  ·  "
            "folio page add|insert|edit …  ·  (alias: book …)"
        ),
    )


def _book_page_sub(world: World, rest: str) -> CommandResult:
    if not rest:
        return CommandResult(
            True,
            fmt.hint(
                "Usage: book page add <book> [title |] body  ·  "
                "book page insert <book> <n> [title |] body  ·  "
                "book page edit <book> <n> [studio |] body  ·  "
                "book page add <book> <title> <<studio"
            ),
        )
    parts = rest.split(maxsplit=1)
    action = parts[0].lower()
    tail = parts[1].strip() if len(parts) > 1 else ""
    if action not in ("add", "append", "insert", "edit", "set", "body"):
        return CommandResult(
            True,
            fmt.hint(
                "Usage: book page add|insert|edit …  ·  "
                "studio | body  or  <<studio multiline"
            ),
        )
    if not tail:
        return CommandResult(True, fmt.hint("Name a book and page content."))

    if action in ("edit", "set", "body"):
        return _book_page_edit(world, tail)

    if action == "insert":
        # book page insert <book…> <pos> <content>
        # book name may be multi-word until we find a position token then content
        tokens = tail.split()
        if len(tokens) < 3:
            return CommandResult(
                True,
                fmt.hint("Usage: book page insert <book> <position> [title |] body"),
            )
        # find first integer token as position
        pos_i = None
        pos_val = None
        for i, tok in enumerate(tokens):
            if tok.isdigit():
                pos_i = i
                pos_val = int(tok)
                break
        if pos_i is None or pos_val is None:
            return CommandResult(True, fmt.hint("Insert needs a 1-based page position."))
        book_name = " ".join(tokens[:pos_i]).strip()
        content = " ".join(tokens[pos_i + 1 :]).strip()
        book, err = _resolve_book_here(world, book_name)
        if err:
            return CommandResult(True, err)
        assert book is not None
        parsed = _parse_book_page_content(content)
        if not parsed:
            return CommandResult(
                True, fmt.hint("Page content: [title |] body  (\\n for line breaks)")
            )
        title, body = parsed
        try:
            pid = world.add_book_page(book.id, title, body, position=pos_val)
        except ValueError as e:
            return CommandResult(True, fmt.err(str(e)))
        _push_book_page_delete_undo(
            world, book.id, pid, f"book page insert {book.name}"
        )
        pages = world.list_book_pages(book.id)
        return CommandResult(
            True,
            fmt.ok(
                f"Inserted page at {pos_val} · {book.name}  "
                f"({len(pages)} page(s)) · {pid}"
            ),
        )

    # add / append: first token(s) book name until we have content with |
    # Prefer: book page add <book> | title | body  OR  book page add <book> title | body
    # Studio: book page add <book> Title | studio | body  (via parse_lore_add peel)
    book, content = _split_book_and_content(world, tail)
    if book is None:
        return CommandResult(True, fmt.err(f"No book matching start of {tail!r}."))
    parsed = _parse_book_page_content(content)
    if not parsed:
        return CommandResult(
            True,
            fmt.hint(
                "Page content: [title |] body  ·  title | studio | body  ·  "
                "\\n for line breaks  ·  book page add <book> <title> <<studio"
            ),
        )
    title, body = parsed
    pid = world.add_book_page(book.id, title, body, position=None)
    _push_book_page_delete_undo(world, book.id, pid, f"book page add {book.name}")
    pages = world.list_book_pages(book.id)
    from .studio_text import is_studio

    note = "  ·  studio text" if is_studio(body) else ""
    return CommandResult(
        True,
        fmt.ok(f"Page added · {book.name}  page {len(pages)} · {pid}{note}"),
    )


def _parse_book_page_content(content: str) -> tuple[str, str] | None:
    """
    Parse page title + body with optional studio.

    Forms:
      title | body
      title | studio | body
      studio | body
      body
    """
    from .studio_text import peel_studio_prefix, prepare_stored_text

    content = (content or "").strip()
    if not content:
        return None
    want_studio, rest = peel_studio_prefix(content)
    title = ""
    body = rest
    if "|" in rest:
        left, _, right = rest.partition("|")
        left, right = left.strip(), right.strip()
        st2, right2 = peel_studio_prefix(right)
        if st2:
            want_studio = True
            title, body = left, right2
        else:
            # title | body  OR  title | studio | body already handled by peel on right
            title, body = left, right
            st3, body3 = peel_studio_prefix(body)
            if st3:
                want_studio = True
                body = body3
    body = unescape_desc(body)
    if not body.strip() and not title:
        return None
    if not body.strip() and title:
        # title-only with empty body allowed for chapter shell
        body = ""
    body = prepare_stored_text(body, studio=want_studio)
    return title, body


def _book_page_edit(world: World, tail: str) -> CommandResult:
    """
    book page edit <book> <n> [studio |] body
    Replace body of 1-based page n (chapter section).
    """
    from .studio_text import is_studio, peel_studio_prefix, prepare_stored_text
    from .textutil import unescape_desc

    tokens = tail.split()
    if len(tokens) < 3:
        return CommandResult(
            True,
            fmt.hint("Usage: book page edit <book> <n> [studio |] body"),
        )
    # first digit = page number
    page_i = None
    page_val = None
    for i, tok in enumerate(tokens):
        if tok.isdigit():
            page_i = i
            page_val = int(tok)
            break
    if page_i is None or page_val is None:
        return CommandResult(True, fmt.hint("Edit needs a 1-based page number."))
    book_name = " ".join(tokens[:page_i]).strip()
    content = " ".join(tokens[page_i + 1 :]).strip()
    book, err = _resolve_book_here(world, book_name)
    if err:
        return CommandResult(True, err)
    assert book is not None
    want_studio, content = peel_studio_prefix(content)
    # If still "title | body", use part after last useful peel as body
    if "|" in content:
        _left, _, right = content.partition("|")
        right = right.strip()
        st2, right = peel_studio_prefix(right)
        want_studio = want_studio or st2
        body_raw = right if right else content
    else:
        body_raw = content
    body = unescape_desc(body_raw)
    body = prepare_stored_text(body, studio=want_studio)
    try:
        page = world._book_page_row(book.id, page_val)
        prior = page["body"] or ""
        world.set_book_page_body(book.id, page_val, body)
    except ValueError as e:
        return CommandResult(True, fmt.err(str(e)))
    _push_book_page_body_undo(
        world, page["id"], prior, f"book page edit {book.name} {page_val}"
    )
    note = "  ·  studio text" if is_studio(body) else ""
    return CommandResult(
        True,
        fmt.ok(f"Page {page_val} body updated · {book.name}{note}"),
    )


def _split_book_and_content(world: World, tail: str):
    """Find longest prefix that resolves uniquely to a folio; remainder is page content."""
    tokens = tail.split()
    for i in range(len(tokens), 0, -1):
        name = " ".join(tokens[:i])
        content = " ".join(tokens[i:]).strip()
        if not content:
            continue
        matches = world.resolve_here_matches(name, kind="folio")
        if not matches:
            matches = world.resolve_here_matches(name, kind="book")
        if len(matches) == 1:
            return matches[0], content
        if len(matches) > 1:
            return None, tail  # caller sees generic fail; prefer explicit qualify
    matches = world.resolve_here_matches(tail, kind="folio")
    if not matches:
        matches = world.resolve_here_matches(tail, kind="book")
    if len(matches) == 1:
        return matches[0], ""
    return None, tail


def _book_line_ints(tokens: list[str], count: int) -> list[tuple[int, int]] | None:
    """Collect the first ``count`` digit tokens as (index, value)."""
    found: list[tuple[int, int]] = []
    for i, tok in enumerate(tokens):
        if tok.isdigit():
            found.append((i, int(tok)))
            if len(found) == count:
                return found
    return None


def _book_line_sub(world: World, rest: str) -> CommandResult:
    """
    book line insert <book> <page> <line> text
    book line add <book> <page> text
    book line remove <book> <page> <line>
    book line move <book> <page> <from> <to>
    """
    from .book import split_page_lines
    from .textutil import unescape_desc

    usage = (
        "Usage: book line insert <book> <page> <line> text  ·  "
        "book line add <book> <page> text  ·  "
        "book line remove <book> <page> <line>  ·  "
        "book line move <book> <page> <from> <to>"
    )
    if not rest:
        return CommandResult(True, fmt.hint(usage))
    parts = rest.split(maxsplit=1)
    action = parts[0].lower()
    tail = parts[1].strip() if len(parts) > 1 else ""
    if action not in ("insert", "add", "append", "amend", "remove", "rm", "move", "mv"):
        return CommandResult(True, fmt.hint(usage))
    if not tail:
        return CommandResult(True, fmt.hint("Name a book, page, and line args."))

    tokens = tail.split()

    if action in ("remove", "rm"):
        ints = _book_line_ints(tokens, 2)
        if ints is None or len(tokens) < 3:
            return CommandResult(
                True,
                fmt.hint("Usage: book line remove <book> <page> <line>"),
            )
        (page_i, page_val), (line_i, line_val) = ints[0], ints[1]
        book_name = " ".join(tokens[:page_i]).strip()
        if not book_name or line_i != page_i + 1:
            # require page then line after book name
            if not book_name:
                return CommandResult(
                    True,
                    fmt.hint("Usage: book line remove <book> <page> <line>"),
                )
        book, err = _resolve_book_here(world, book_name)
        if err:
            return CommandResult(True, err)
        assert book is not None
        try:
            page_row = world._book_page_row(book.id, page_val)
            prior_body = page_row["body"] or ""
            row = world.remove_book_page_line(book.id, page_val, line_val)
        except ValueError as e:
            return CommandResult(True, fmt.err(str(e)))
        _push_book_page_body_undo(
            world, page_row["id"], prior_body, f"book line remove {book.name}"
        )
        n_lines = len(split_page_lines(row["body"] or ""))
        return CommandResult(
            True,
            fmt.ok(
                f"Line removed · {book.name} page {page_val}  "
                f"was line {line_val} → {n_lines} line(s)"
            ),
        )

    if action in ("move", "mv"):
        ints = _book_line_ints(tokens, 3)
        if ints is None:
            return CommandResult(
                True,
                fmt.hint("Usage: book line move <book> <page> <from> <to>"),
            )
        (page_i, page_val), (_fi, from_val), (_ti, to_val) = ints[0], ints[1], ints[2]
        book_name = " ".join(tokens[:page_i]).strip()
        if not book_name:
            return CommandResult(
                True,
                fmt.hint("Usage: book line move <book> <page> <from> <to>"),
            )
        book, err = _resolve_book_here(world, book_name)
        if err:
            return CommandResult(True, err)
        assert book is not None
        try:
            page_row = world._book_page_row(book.id, page_val)
            prior_body = page_row["body"] or ""
            row = world.move_book_page_line(book.id, page_val, from_val, to_val)
        except ValueError as e:
            return CommandResult(True, fmt.err(str(e)))
        _push_book_page_body_undo(
            world, page_row["id"], prior_body, f"book line move {book.name}"
        )
        n_lines = len(split_page_lines(row["body"] or ""))
        return CommandResult(
            True,
            fmt.ok(
                f"Line moved · {book.name} page {page_val}  "
                f"{from_val} → {to_val}  ({n_lines} line(s))"
            ),
        )

    if action in ("add", "append"):
        # book line add <book…> <page> text…
        if len(tokens) < 3:
            return CommandResult(
                True,
                fmt.hint("Usage: book line add <book> <page> text"),
            )
        page_i = None
        page_val = None
        for i, tok in enumerate(tokens):
            if tok.isdigit():
                page_i = i
                page_val = int(tok)
                break
        if page_i is None or page_val is None:
            return CommandResult(True, fmt.hint("Line add needs a 1-based page number."))
        book_name = " ".join(tokens[:page_i]).strip()
        text_raw = " ".join(tokens[page_i + 1 :]).strip()
        book, err = _resolve_book_here(world, book_name)
        if err:
            return CommandResult(True, err)
        assert book is not None
        text = unescape_desc(text_raw)
        if not text.strip():
            return CommandResult(True, fmt.hint("Line text must not be empty."))
        pages = world.list_book_pages(book.id)
        if not pages or page_val < 1 or page_val > len(pages):
            return CommandResult(
                True,
                fmt.err(
                    f"Page {page_val} out of range "
                    f"(book has {len(pages)} page(s))."
                ),
            )
        page_row = pages[page_val - 1]
        prior_body = page_row["body"] or ""
        existing = split_page_lines(prior_body)
        line_at = len(existing) + 1
        try:
            row = world.insert_book_page_lines(book.id, page_val, line_at, text)
        except ValueError as e:
            return CommandResult(True, fmt.err(str(e)))
        _push_book_page_body_undo(
            world, page_row["id"], prior_body, f"book line add {book.name}"
        )
        n_lines = len(split_page_lines(row["body"] or ""))
        added = len(split_page_lines(text)) or 1
        return CommandResult(
            True,
            fmt.ok(
                f"Line(s) added · {book.name} page {page_val}  "
                f"at end → {n_lines} line(s)  (+{added})"
            ),
        )

    # insert / amend: book line insert <book…> <page> <line> text…
    if len(tokens) < 4:
        return CommandResult(
            True,
            fmt.hint("Usage: book line insert <book> <page> <line> text"),
        )
    ints = _book_line_ints(tokens, 2)
    if ints is None:
        return CommandResult(
            True,
            fmt.hint("Line insert needs 1-based page and line positions."),
        )
    (page_i, page_val), (line_i, line_val) = ints[0], ints[1]
    book_name = " ".join(tokens[:page_i]).strip()
    text_raw = " ".join(tokens[line_i + 1 :]).strip()
    if not book_name or not text_raw:
        return CommandResult(
            True,
            fmt.hint("Usage: book line insert <book> <page> <line> text"),
        )
    book, err = _resolve_book_here(world, book_name)
    if err:
        return CommandResult(True, err)
    assert book is not None
    text = unescape_desc(text_raw)
    if not text.strip():
        return CommandResult(True, fmt.hint("Line text must not be empty."))
    try:
        page_row = world._book_page_row(book.id, page_val)
        prior_body = page_row["body"] or ""
        row = world.insert_book_page_lines(book.id, page_val, line_val, text)
    except ValueError as e:
        return CommandResult(True, fmt.err(str(e)))
    _push_book_page_body_undo(
        world, page_row["id"], prior_body, f"book line insert {book.name}"
    )
    n_lines = len(split_page_lines(row["body"] or ""))
    return CommandResult(
        True,
        fmt.ok(
            f"Line(s) inserted · {book.name} page {page_val}  "
            f"at line {line_val} → {n_lines} line(s)"
        ),
    )


def _book_pages_list(world: World, book) -> str:
    from .book import format_status_markup

    pages = world.list_book_pages(book.id)
    status = world.book_status(book.id)
    ref = world.short_ref_of(book.id)
    lines = [
        fmt.title_line(book.name, kind=book.ven_kind or "folio"),
        (
            f"[dim]#{fmt.safe(ref)}  ·  {len(pages)} leaf/page(s)  ·  [/dim]"
            f"{format_status_markup(status)}"
            f"[dim]  ·  {fmt.safe(world.where_label(book.id))}  ·  "
            f"folio open {fmt.safe(book.name)}#{fmt.safe(ref)}[/dim]"
        ),
    ]
    if not pages:
        lines.append(fmt.hint("No leaves yet.  folio page add …"))
        return fmt.join_blocks(*lines, gap=0)
    lines.append(fmt.section("Leaves"))
    for p in pages:
        ttl = p["title"] or f"Page {p['position']}"
        lines.append(fmt.bullet(f"{p['position']}. {ttl}", kind="folio"))
    return "\n".join(lines)


def _book_read_text(world: World, book, index: int = 0) -> str:
    from .book import format_page_view
    from .ids import display_name

    pages = world.list_book_pages(book.id)
    status = world.book_status(book.id)
    if not pages:
        view = format_page_view(
            book_name=display_name(book.name),
            status=status,
            page_index=0,
            page_count=0,
            title="",
            body="",
        )
        return fmt.join_blocks(
            view,
            fmt.hint("Add leaves: folio page add …"),
            gap=0,
        )
    index = max(0, min(index, len(pages) - 1))
    page = pages[index]
    view = format_page_view(
        book_name=display_name(book.name),
        status=status,
        page_index=index,
        page_count=len(pages),
        title=page["title"] or "",
        body=page["body"] or "",
    )
    # view already contains safe Rich markup (user text escaped inside formatter)
    return fmt.join_blocks(
        view,
        fmt.hint(
            "TUI: soft reader · ←/→ leaves · + add · e edit · Esc closes  ·  "
            "REPL: folio pages …"
        ),
        gap=0,
    )


def _parse_lore_title_body(rest: str) -> tuple[str, str] | None:
    rest = rest.strip()
    if not rest:
        return None
    if "|" in rest:
        title, body = rest.split("|", 1)
        title, body = title.strip(), body.strip()
    else:
        title, body = "", rest
    if not body:
        return None
    return title, body


def parse_lore_add(rest: str) -> tuple[str, str, str | None] | None:
    """
    Parse lore add payload → (title, body, when_label).

    Optional author when-stamp (mythic / date / unix free text), kept separate
    from wall-clock created_at:

      lore add when <stamp> | [title |] body
      lore add @<stamp> | [title |] body
      lore add [title |] body          # no stamp
      lore add studio | [title |] body # Studio Text body

    Examples:
      when Before the Roads | Founding | Raised for travelers.
      @1704067200 | Note | Something shifted.
      @2024-06-15 14:30 | | Body only with a date stamp.
      Founding | Raised for travelers.
      studio | Note | **Bold** body with [[wikilink]]
    """
    from .studio_text import peel_studio_prefix, prepare_stored_text

    rest = rest.strip()
    if not rest:
        return None
    want_studio, rest = peel_studio_prefix(rest)
    when_label: str | None = None
    low = rest.lower()
    if low.startswith("when "):
        rest = rest[5:].strip()
        if "|" not in rest:
            return None
        stamp, rest = rest.split("|", 1)
        when_label = stamp.strip() or None
        rest = rest.strip()
    elif rest.startswith("@"):
        rest = rest[1:]
        if "|" not in rest:
            return None
        stamp, rest = rest.split("|", 1)
        when_label = stamp.strip() or None
        rest = rest.strip()

    # second chance: studio after when stamp
    if not want_studio:
        want_studio, rest = peel_studio_prefix(rest)

    parsed = _parse_lore_title_body(rest)
    if not parsed:
        return None
    title, body = parsed
    # Same line-break escapes as @desc: \n → newline, \\ → \
    title = unescape_desc(title)
    body = unescape_desc(body)
    body = prepare_stored_text(body, studio=want_studio)
    if when_label:
        when_label = unescape_desc(when_label)
    return title, body, when_label


def _lore_meta_line(row) -> str:
    """Story when-stamp (if any) plus typed-at wall clock and author."""
    stamp = (row["when_label"] or "").strip()
    typed = row["created_at"] or ""
    author = row["author"] or "builder"
    if stamp:
        return f"{stamp}  ·  typed {typed}  ·  {author}"
    return f"typed {typed}  ·  {author}"


def _record_subject_history(
    world: World,
    subject_type: str,
    subject_id: str,
    *,
    verb: str,
    story_when: str,
    node_index: int | None,
    note: str = "",
    place_instance_id: str | None = None,
    realm_instance_id: str | None = None,
    timeline_instance_id: str | None = None,
    event_code: str | None = None,
) -> str:
    """
    Write a life-of-material history row (best-effort place + strand).

    Returns the shared event_code (new HST-NNN unless *event_code* given).
    """
    from .story_when import resolve_history_where

    where = resolve_history_where(
        world,
        place_instance_id=place_instance_id,
        realm_instance_id=realm_instance_id,
        timeline_instance_id=timeline_instance_id,
    )
    world.record_history(
        subject_type,
        subject_id,
        verb=verb,
        story_when=story_when,
        node_index=node_index,
        place_instance_id=where["place_instance_id"],
        place_name=where["place_name"] or "",
        realm_instance_id=where["realm_instance_id"],
        realm_name=where["realm_name"] or "",
        timeline_instance_id=where["timeline_instance_id"],
        timeline_name=where["timeline_name"] or "",
        note=note,
        event_code=event_code,
    )
    # Read back code from the latest row for this subject (or use given)
    if event_code:
        return event_code.strip().upper()
    rows = world.history_for(subject_type, subject_id)
    if rows:
        return (rows[-1]["event_code"] or "").strip().upper()
    return ""


def _peel_and_story_when(text: str) -> tuple[str, str, int | None]:
    from .story_when import peel_story_when_suffix

    return peel_story_when_suffix(text)


def _story_when_for_lore_label(when_label: str | None) -> tuple[str, int | None]:
    from .story_when import story_when_from_lore_label

    return story_when_from_lore_label(when_label)


def _indent_lore_body(markup: str, *, spaces: int = 2) -> str:
    """Pad each line of lore body two spaces past the title column."""
    pad = " " * max(0, spaces)
    if not markup:
        return markup
    return "\n".join(
        (pad + line) if line.strip() else line for line in markup.split("\n")
    )


def _format_dialog_lore_entry(row) -> str:
    """
    Compact, dim dialog-pointer row for lore lists.

    Full transcript lives under dialogs show — avoid dumping meta as loud prose.
    """
    title = row["title"] or "Dialog"
    body = (row["body"] or "").strip()
    who = ""
    handle = ""
    for line in body.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("a dialog took place between "):
            who = s[len("A dialog took place between ") :].rstrip(".")
        elif low.startswith("transcript:") and not low.startswith("transcript id:"):
            # Cute slug line (preferred for typing)
            handle = s.split(":", 1)[1].strip()
        elif low.startswith("re-read:"):
            rest = s.split(":", 1)[1].strip()
            if "dialogs show" in rest.lower():
                bits = rest.split()
                if bits:
                    handle = bits[-1]
        elif low.startswith("transcript id:") and not handle:
            # Legacy fallback (opaque dlg_… id)
            handle = s.split(":", 1)[1].strip()
    bits: list[str] = []
    if who:
        bits.append(who)
    if handle:
        bits.append(f"dialogs show {handle}")
    else:
        bits.append("dialogs show …")
    detail = "  ·  ".join(bits)
    return (
        f"[bold]{fmt.safe(title)}[/bold]  "
        f"[dim]{fmt.safe(_lore_meta_line(row))}[/dim]\n"
        + _indent_lore_body(f"[dim]{fmt.safe(detail)}[/dim]")
    )


def _format_lore_rows(heading: str, rows: list) -> str:
    if not rows:
        return fmt.hint(f"No lore revisions yet for {heading}.")
    # heading may include slug; title_line display_name's cute segments in the name part
    blocks: list[str] = [fmt.title_line(heading)]
    for r in rows:
        author = (r["author"] or "").strip().lower()
        if author == "dialog":
            blocks.append(_format_dialog_lore_entry(r))
            continue
        title = r["title"] or "Revision"
        # Title + meta at column 0; body two spaces deeper
        entry = fmt.join_blocks(
            f"[bold]{fmt.safe(title)}[/bold]  "
            f"[dim]{fmt.safe(_lore_meta_line(r))}[/dim]",
            _indent_lore_body(fmt.prose(r["body"])),
            gap=0,
        )
        blocks.append(entry)
    return fmt.join_blocks(*blocks, gap=1)


_LORE_ADD_USAGE = (
    "Usage: lore add [when <stamp> | | @<stamp> |] [title |] body\n"
    "  e.g. lore add when Before the Roads | Founding | Raised for travelers.\n"
    "       lore add @1704067200 | Note | Something shifted.\n"
    "       lore add Founding | Raised for travelers.\n"
    "       lore add from field-notes 1:2\n"
    "       lore add from field-notes p1:3 | Optional title\n"
    "       lore on <item>  ·  lore on <item> add [when … |] [title |] body"
)


def _layer_keyword_kind(query: str) -> str | None:
    """Map realm/timeline shorthand to layer kind, or None."""
    low = " ".join((query or "").lower().split())
    if low in ("realm", "this realm", "here realm"):
        return "realm"
    if low in ("timeline", "this timeline", "here timeline", "time", "tl"):
        return "timeline"
    return None


def _resolve_instance_target(world: World, query: str):
    """
    Resolve here/inv, current realm/timeline keywords, named layers, or unique global.
    """
    q = (query or "").strip()
    if not q:
        return None, fmt.err("No match for empty name.")

    # Player self: me / self / i / you / player
    if q.lower() in ("me", "self", "i", "you", "player"):
        player = _player_instance(world)
        if player is None:
            return None, fmt.hint("No player set.")
        return player, None

    # Current place's layer coords (not "things here")
    layer_kind = _layer_keyword_kind(q)
    if layer_kind is not None:
        loc = world.player_location()
        if loc is None:
            return None, fmt.hint("Nowhere.")
        inst = world.current_layer_instance(layer_kind)
        if inst is None:
            return None, fmt.err(
                f"This place has no {layer_kind}.  "
                f"{layer_kind} set <name>"
            )
        return inst, None

    thing, err = _resolve_one(world, q)
    if thing is not None:
        return thing, None
    if err and thing is None:
        found = world.find_instances_by_name(q)
        if len(found) == 1:
            return found[0], None
        if len(found) > 1:
            return None, _format_ambiguous(world, q, found)
        # Named realm/timeline layer (catalog), e.g. lore on Unformed
        for kind in ("realm", "timeline"):
            layer = world.resolve_layer(kind, q)
            if layer is not None:
                return layer, None
        return None, err or fmt.err(f"No match for {q!r}.")
    return None, err or fmt.err(f"No match for {q!r}.")


def _split_instance_target_and_rest(
    world: World, tail: str
) -> tuple[InstanceView | None, str, str | None]:
    """
    Longest resolvable instance name prefix; remainder is command rest.

    Description operators (``+``, ``++``, ``clear``, ``add``) never count as
    part of the name so ``@desc on quill + more`` appends rather than matching
    a fuzzy name that absorbs the ``+``.

    Returns (instance|None, rest, error_message|None).
    """
    tail = tail.strip()
    if not tail:
        return None, "", fmt.hint("Name an instance (here or inv).")
    tokens = tail.split()
    # Cap name tokens before a trailing desc operator (if present)
    name_end = len(tokens)
    for i, tok in enumerate(tokens):
        low = tok.lower()
        if low in ("clear", "add") or tok in ("+", "++") or tok.startswith("++"):
            # operator only if not the entire query (allow names that are weird)
            if i > 0:
                name_end = i
                break
        if tok.startswith("+") and i > 0:
            name_end = i
            break
    last_err: str | None = None
    for i in range(name_end, 0, -1):
        name = " ".join(tokens[:i])
        rest = " ".join(tokens[i:]).strip()
        thing, err = _resolve_instance_target(world, name)
        if thing is not None:
            return thing, rest, None
        if err:
            last_err = err
            plain_err = fmt.plain(err).lower() if err else ""
            if "ambiguous" in plain_err:
                return None, tail, err
    return None, tail, last_err or fmt.err(f"No instance matching start of {tail!r}.")


def _lore_add_from_book(world: World, rest: str) -> str:
    """
    lore add from <book> <page>:<line> [| optional title]

    Copies the book line body into place lore with a citation title by default.
    """
    from .book import parse_book_line_ref
    from .ids import display_name

    rest = rest.strip()
    if not rest:
        return fmt.hint(
            "Usage: lore add from <book> <page>:<line>  [| optional title]"
        )
    title_override: str | None = None
    payload = rest
    if "|" in rest:
        payload, _, title_part = rest.partition("|")
        payload = payload.strip()
        title_override = title_part.strip() or None

    tokens = payload.split()
    if len(tokens) < 2:
        return fmt.hint(
            "Usage: lore add from <book> <page>:<line>  e.g. lore add from notes 1:2"
        )

    # Last token that parses as page:line is the ref; book name is the prefix
    ref_i = None
    page_val = line_val = None
    for i in range(len(tokens) - 1, -1, -1):
        parsed_ref = parse_book_line_ref(tokens[i])
        if parsed_ref is not None:
            ref_i = i
            page_val, line_val = parsed_ref
            break
    if ref_i is None or page_val is None or line_val is None:
        return fmt.hint(
            "Need a page:line ref (1:2 or p1:2).  "
            "Usage: lore add from <book> <page>:<line>"
        )
    book_name = " ".join(tokens[:ref_i]).strip()
    if not book_name:
        return fmt.hint("Name a book before the page:line ref.")
    book, err = _resolve_book_here(world, book_name)
    if err:
        return err
    assert book is not None
    try:
        line_text = world.get_book_line_text(book.id, page_val, line_val)
    except ValueError as e:
        return fmt.err(str(e))

    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")

    bname = display_name(book.name)
    default_title = f"{bname} p{page_val}:{line_val}"
    title = title_override if title_override is not None else default_title
    body = line_text
    lid = world.add_lore(
        "instance",
        loc.id,
        body=body,
        title=title,
        timeline_instance_id=loc.timeline_instance_id,
        when_label=None,
        author="builder",
    )
    world.undo_stack.push(
        f"lore add from {book.name} {page_val}:{line_val}",
        lambda w, lid=lid: w.delete_lore(lid),
    )
    return fmt.ok(
        f"Lore from book · {default_title} → place  ·  {lid}"
    )


def _lore_on_instance(world: World, rest: str) -> str:
    """
    lore on <instance>
    lore on <instance> add [when … |] [title |] body
    """
    rest = rest.strip()
    if not rest:
        return fmt.hint(
            "Usage: lore on <item|person|realm|timeline>  ·  "
            "lore on <match> add [when <stamp> |] [title |] body"
        )
    lower = rest.lower()
    if " add " in lower:
        idx = lower.index(" add ")
        target_q, add_rest = rest[:idx].strip(), rest[idx + 5 :].strip()
        thing, err = _resolve_instance_target(world, target_q)
        if err or thing is None:
            return err or fmt.err(f"No match for {target_q!r}.")
        add_rest, sw_peel, ni_peel = _peel_and_story_when(add_rest)
        parsed = parse_lore_add(add_rest)
        if not parsed:
            return fmt.hint(
                "Usage: lore on <match> add [when <stamp> | | @stamp |] "
                "[title |] body  [when @N]"
            )
        title, body, when_label = parsed
        sw, ni = _story_when_for_lore_label(when_label)
        if sw_peel != "@unknown":
            sw, ni = sw_peel, ni_peel
        timeline_id = thing.timeline_instance_id
        if timeline_id is None:
            loc = world.player_location()
            timeline_id = loc.timeline_instance_id if loc else None
        lid = world.add_lore(
            "instance",
            thing.id,
            body=body,
            title=title,
            timeline_instance_id=timeline_id,
            when_label=when_label,
            author="builder",
        )
        world.undo_stack.push(
            f"lore on {thing.name}",
            lambda w, lid=lid: w.delete_lore(lid),
        )
        _record_subject_history(
            world,
            "lore",
            lid,
            verb="lore",
            story_when=sw,
            node_index=ni,
            note=title or thing.name,
            realm_instance_id=thing.realm_instance_id,
            timeline_instance_id=timeline_id,
        )
        stamp_note = f"  ·  {when_label}" if when_label else ""
        ref = world.short_ref_of(thing.id)
        return fmt.ok(
            f"Lore on instance · {fmt.named_ref(thing.name, ref)}  ·  "
            f"{lid}{stamp_note}  ·  story {sw}"
        )

    thing, err = _resolve_instance_target(world, rest)
    if err or thing is None:
        return err or fmt.err(f"No match for {rest!r}.")
    rows = world.lore_for("instance", thing.id)
    ref = world.short_ref_of(thing.id)
    heading = f"{fmt.named_ref(thing.name, ref)}  (instance)"
    if not rows:
        return fmt.join_blocks(
            fmt.title_line(heading),
            fmt.hint(
                "No instance lore yet.  "
                f"lore on {thing.name} add Title | body  ·  "
                "does not require elevate"
            ),
            gap=0,
        )
    return _format_lore_rows(heading, rows)


def _lore_add_flags(world: World, arg: str) -> str:
    """
    Flag form for new lore entries::

      lore -a -t Founding -b Raised for travelers. -w 0
      lore --add --on cartographer -n Note -d Soft light. --when 1
      lore on quill -a -t Note -b Bent nib.

    -a / --add is required. Title: -t/-n/--title/--name.
    Body: -b/--body or -d/--desc. When: -w/--when.
    Target: --on <match>, or leading ``on <match>`` before flags.
    """
    from .argflags import LORE_FLAG_ALIASES, parse_named_flags, story_when_from_flag
    from .studio_text import prepare_stored_text

    raw = (arg or "").strip()
    # lore on <match> -a …
    if raw.lower().startswith("on "):
        thing, rest, err = _split_instance_target_and_rest(world, raw[3:])
        if err or thing is None:
            return err or fmt.hint(
                "Usage: lore on <match> -a -t <title> -b <body> [-w N]"
            )
        target_inst = thing
        flag_src = rest
    else:
        target_inst = None
        flag_src = raw

    parsed = parse_named_flags(flag_src, aliases=LORE_FLAG_ALIASES)
    if parsed.error:
        return fmt.err(parsed.error)
    if "add" not in parsed.flags:
        return fmt.hint(
            "Lore flags need -a / --add to create an entry.\n"
            "  lore -a -t Founding -b Raised for travelers. -w 0\n"
            "  lore --add --on me -n Note -d Soft light.\n"
            "  Prose still works: lore add Title | body"
        )
    title = (parsed.get("name") or "").strip()
    body = (parsed.get("body") or parsed.get("desc") or "").strip()
    if not body and parsed.positionals:
        body = " ".join(parsed.positionals).strip()
    if not body:
        return fmt.hint(
            "Usage: lore -a -t <title> -b <body> [-w N]\n"
            "  Body required (-b / --body / -d / --desc)."
        )
    body = prepare_stored_text(unescape_desc(body), studio=False)
    title = unescape_desc(title) if title else ""

    story_when = "@unknown"
    node_index: int | None = None
    when_label: str | None = None
    if "when" in parsed.flags:
        story_when, node_index = story_when_from_flag(parsed.get("when"))
        if story_when != "@unknown":
            when_label = story_when
        elif (parsed.get("when") or "").strip():
            # freeform mythic stamp
            when_label = parsed.get("when").strip()
            story_when, node_index = _story_when_for_lore_label(when_label)

    # Target: --on, resolved on-prefix, or current place
    if target_inst is None:
        on_q = parsed.get("on")
        if on_q:
            thing, err = _resolve_instance_target(world, on_q)
            if err or thing is None:
                return err or fmt.err(f"No match for {on_q!r}.")
            target_inst = thing
        else:
            loc = world.player_location()
            if not loc:
                return fmt.hint("Nowhere.")
            target_inst = loc

    subject_type = "instance"
    subject_id = target_inst.id
    lid = world.add_lore(
        subject_type,
        subject_id,
        body=body,
        title=title,
        timeline_instance_id=target_inst.timeline_instance_id,
        when_label=when_label,
        author="builder",
    )
    world.undo_stack.push(
        f"lore add {display_name(target_inst.name)}",
        lambda w, lid=lid: w.delete_lore(lid),
    )
    _record_subject_history(
        world,
        "lore",
        lid,
        verb="lore",
        story_when=story_when,
        node_index=node_index,
        note=title or display_name(target_inst.name),
        realm_instance_id=target_inst.realm_instance_id,
        timeline_instance_id=target_inst.timeline_instance_id,
    )
    ref = world.short_ref_of(target_inst.id)
    stamp_note = f"  ·  {when_label}" if when_label else ""
    return fmt.ok(
        f"Lore · {fmt.named_ref(display_name(target_inst.name), ref)}  ·  "
        f"{lid}{stamp_note}  ·  story {story_when}"
    )


def _lore(world: World, arg: str) -> str:
    """
    Place instance (default):
      lore
      lore add [when <stamp> | | @stamp |] [title |] body
      lore -a -t Title -b body [-w N]
      lore add from <book> <page>:<line> [| title]
      lore search <q>

    Any instance (item/person/place copy — no elevate required):
      lore on <match>
      lore on <match> add [when … |] [title |] body
      lore on <match> -a -t … -b …
      lore --add --on <match> …

    Prime VEN:
      lore ven <slug-or-name>
      lore ven <slug-or-name> add [when … |] [title |] body
    """
    from .argflags import looks_like_flag_command

    arg = arg.strip()

    # Flag form (free order): lore -a …  ·  lore on x -a …
    if looks_like_flag_command(arg):
        return _lore_add_flags(world, arg)

    # Shorthand: lore realm … → lore on realm …
    low0 = arg.lower()
    if low0 == "realm" or low0.startswith("realm "):
        return _lore(world, "on " + arg)
    if low0 == "timeline" or low0.startswith("timeline "):
        return _lore(world, "on " + arg)

    # ── VEN-targeted lore ───────────────────────────────────────────────
    if arg.lower().startswith("ven "):
        rest = arg[4:].strip()
        if not rest:
            return fmt.hint(
                "Usage: lore ven <slug-or-name>  |  "
                "lore ven <slug-or-name> add [when <stamp> |] [title |] body"
            )
        # add subcommand: lore ven <target> add ...
        # target may be multi-word until " add "
        lower = rest.lower()
        if " add " in lower:
            idx = lower.index(" add ")
            target, add_rest = rest[:idx].strip(), rest[idx + 5 :].strip()
            add_rest, sw_peel, ni_peel = _peel_and_story_when(add_rest)
            parsed = parse_lore_add(add_rest)
            if not parsed:
                return fmt.hint(
                    "Usage: lore ven <slug> add [when <stamp> | | @stamp |] "
                    "[title |] body  [when @N]"
                )
            title, body, when_label = parsed
            sw, ni = _story_when_for_lore_label(when_label)
            if sw_peel != "@unknown":
                sw, ni = sw_peel, ni_peel
            ven = world.find_ven(target)
            if not ven:
                return fmt.err(
                    f"No VEN matching {target!r}.  Use vens to list slugs."
                )
            lid = world.add_lore(
                "ven",
                ven.id,
                body=body,
                title=title,
                when_label=when_label,
                author="builder",
            )
            world.undo_stack.push(
                f"lore ven {ven.slug}",
                lambda w, lid=lid: w.delete_lore(lid),
            )
            _record_subject_history(
                world,
                "lore",
                lid,
                verb="lore",
                story_when=sw,
                node_index=ni,
                note=title or ven.name,
            )
            stamp_note = f"  ·  {when_label}" if when_label else ""
            return fmt.ok(
                f"Lore on VEN · {ven.name} ({ven.slug}) · {lid}"
                f"{stamp_note}  ·  story {sw}"
            )
        # list
        ven = world.find_ven(rest)
        if not ven:
            return fmt.err(f"No VEN matching {rest!r}.  Use vens to list slugs.")
        rows = world.lore_for("ven", ven.id)
        return _format_lore_rows(f"{ven.name} [{ven.slug}]", rows)

    # ── any instance (item/person/…) ────────────────────────────────────
    if arg.lower().startswith("on "):
        return _lore_on_instance(world, arg[3:])

    # ── place instance: add from book line ─────────────────────────────
    if arg.lower().startswith("add from "):
        return _lore_add_from_book(world, arg[9:])

    # ── place instance: add ─────────────────────────────────────────────
    if arg.lower().startswith("add "):
        # avoid treating "add from" twice (already handled)
        add_rest, sw_peel, ni_peel = _peel_and_story_when(arg[4:])
        parsed = parse_lore_add(add_rest)
        if not parsed:
            return fmt.hint(_LORE_ADD_USAGE)
        title, body, when_label = parsed
        sw, ni = _story_when_for_lore_label(when_label)
        if sw_peel != "@unknown":
            sw, ni = sw_peel, ni_peel
        loc = world.player_location()
        if not loc:
            return fmt.hint("Nowhere.")
        lid = world.add_lore(
            "instance",
            loc.id,
            body=body,
            title=title,
            timeline_instance_id=loc.timeline_instance_id,
            when_label=when_label,
            author="builder",
        )
        world.undo_stack.push(
            "lore add",
            lambda w, lid=lid: w.delete_lore(lid),
        )
        _record_subject_history(
            world,
            "lore",
            lid,
            verb="lore",
            story_when=sw,
            node_index=ni,
            note=title or loc.name,
            realm_instance_id=loc.realm_instance_id,
            timeline_instance_id=loc.timeline_instance_id,
        )
        stamp_note = f"  ·  {when_label}" if when_label else ""
        return fmt.ok(
            f"Lore revision recorded · {lid}{stamp_note}  ·  story {sw}"
        )

    if arg.lower().startswith("search "):
        q = arg[7:].strip()
        rows = world.search_lore(q)
        if not rows:
            return fmt.hint("No lore matches.")
        lines = [fmt.section(f"Lore matching “{q}”")]
        for r in rows:
            title = r["title"] or "(untitled)"
            snippet = (r["body"] or "")[:80]
            lines.append(fmt.bullet(f"{title}", _lore_meta_line(r)))
            lines.append(f"      {fmt.safe(snippet)}")
        return "\n".join(lines)

    if arg:
        return fmt.hint(
            "Usage: lore  |  lore add …  |  lore on <item|realm|timeline> …  |  "
            "lore ven <slug> …  |  lore search …"
        )

    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")
    rows = world.lore_for("instance", loc.id)
    if not rows:
        return fmt.hint(
            "No lore for this place yet.  Use: lore add <body>  ·  "
            "lore on <item> add …  ·  help lore"
        )
    return _format_lore_rows(loc.name, rows)


def _dig(world: World, arg: str) -> str:
    """
    dig [place[/subtype]] <name> …   — free-standing place (link after)
    dig bin|box|crate|thing|… <name> [| desc]  — prime + instance **here** (floor)

    Non-place kinds used to be swallowed as place *names* (``dig bin Table`` made
    a free-floating place called \"bin Table\" — not takeable, not put-into).
    """
    if not arg:
        return fmt.hint(
            "Usage:\n"
            "  dig [place/subtype] <place name> [realm …] [timeline …]\n"
            "  dig bin <name> [| desc]   ·  dig box/calendar Q3 2026\n"
            "  dig thing Pink Button | A button she found for him.\n"
            "Places are free-standing (link after). Bins/things land on the floor here."
        )
    loc = world.player_location()
    tokens = arg.strip().split()
    if tokens:
        k, sub = parse_kind_spec(tokens[0])
        # Non-place roots: dig bin Table | … → create + instance on this floor
        if k and k != "place" and k in KINDS:
            rest = " ".join(tokens[1:]).strip()
            if not rest:
                return fmt.hint(
                    f"Usage: dig {k} <name> [| description]\n"
                    f"  e.g. dig bin Table | Oak.  ·  dig {k}/calendar Q3 2026"
                )
            if "|" in rest:
                name_part, _, desc = rest.partition("|")
                name = name_part.strip()
                desc = desc.strip()
            else:
                name = rest
                desc = ""
            if not name:
                return fmt.hint(f"Usage: dig {k} <name> [| description]")
            meta = {"subtype": sub} if sub else None
            ven_id = world.create_ven(name, k, description=desc, meta=meta)
            ven = world.get_ven(ven_id)
            display = ven.name if ven else name
            inst_id = world.instantiate(
                ven_id,
                realm_instance_id=loc.realm_instance_id if loc else None,
                timeline_instance_id=loc.timeline_instance_id if loc else None,
            )
            if loc is not None:
                if is_inner_life_kind(k, sub):
                    slot = default_inner_slot(k, sub)
                else:
                    slot = "interior"
                world.put_in(inst_id, loc.id, slot=slot)

            def undo_dig_here(w: World, iid=inst_id, vid=ven_id) -> None:
                w.delete_instance(iid)
                w.delete_ven(vid)

            world.undo_stack.push(f"dig {display}", undo_dig_here)
            kind_bit = format_kind_label(k, sub)
            ref = world.short_ref_of(inst_id)
            return fmt.join_blocks(
                fmt.ok(f"Dug · {display}  ·  here"),
                fmt.hint(f"{kind_bit}  ·  #{ref}  ·  instance {inst_id}"),
                fmt.hint("take / put / examine  ·  undo to remove"),
                gap=0,
            )

    name, realm_id, timeline_id, subtype = _parse_dig_layers(world, arg, loc)
    meta = {"subtype": subtype} if subtype else None
    ven_id = world.create_ven(name, "place", description="", meta=meta)
    ven = world.get_ven(ven_id)
    display = ven.name if ven else name
    inst = world.instantiate(
        ven_id,
        realm_instance_id=realm_id,
        timeline_instance_id=timeline_id,
    )

    def undo_dig(w: World, inst=inst, ven_id=ven_id) -> None:
        w.delete_instance(inst)
        w.delete_ven(ven_id)

    world.undo_stack.push(f"dig {display}", undo_dig)
    place = world.get_instance(inst)
    coords = world.coords_of(place) if place else None
    kind_bit = format_kind_label("place", subtype)
    return fmt.join_blocks(
        fmt.ok(f"Dug · {display}"),
        fmt.hint(f"{kind_bit}  ·  instance {inst}"),
        fmt.hint(f"coords {coords['label']}" if coords else ""),
        fmt.hint(f"Link with:  link <exit> -> {display} both"),
        gap=0,
    )


def _parse_dig_layers(
    world: World, arg: str, loc
) -> tuple[str, str | None, str | None, str | None]:
    """Parse dig name with optional place/subtype and realm/timeline keywords."""
    tokens = arg.strip().split()
    realm_id = loc.realm_instance_id if loc else None
    timeline_id = loc.timeline_instance_id if loc else None
    subtype: str | None = None
    name_parts: list[str] = []
    i = 0
    # Optional leading place/subtype or place:subtype
    if tokens:
        k, sub = parse_kind_spec(tokens[0])
        if k == "place" and (sub is not None or tokens[0].lower() == "place"):
            # dig place/app Name …  or dig place Name …
            subtype = sub
            i = 1
    while i < len(tokens):
        low = tokens[i].lower()
        if low in ("realm", "timeline") and i + 1 < len(tokens):
            layer_kind = "realm" if low == "realm" else "timeline"
            # consume following tokens until next keyword
            j = i + 1
            layer_parts: list[str] = []
            while j < len(tokens) and tokens[j].lower() not in ("realm", "timeline"):
                layer_parts.append(tokens[j])
                j += 1
            layer_name = " ".join(layer_parts)
            layer = world.resolve_layer(layer_kind, layer_name)
            if layer is None:
                raise ValueError(
                    f"No {layer_kind} matching {layer_name!r}.  "
                    f"Try: {layer_kind} list  or  {layer_kind} create {layer_name}"
                )
            if layer_kind == "realm":
                realm_id = layer.id
            else:
                timeline_id = layer.id
            i = j
            continue
        name_parts.append(tokens[i])
        i += 1
    name = " ".join(name_parts).strip()
    if not name:
        raise ValueError("dig needs a place name")
    return name, realm_id, timeline_id, subtype


def _link(world: World, arg: str) -> str:
    """
    link <exit> -> <place> [type] [both]
    link rename <old> as <new>
    link remove|unlink|delink <exit> [both]   (same as top-level unlink)
    """
    raw = arg.strip()
    if not raw:
        return fmt.hint(
            "Usage: link <exit> -> <place> [type] [both]\n"
            "       link rename <old> as <new>\n"
            "       unlink <exit> [both]  ·  delink <exit> [both]"
        )
    low = raw.lower()
    if low.startswith("rename "):
        return _link_rename(world, raw[7:].strip())
    if low.startswith("remove ") or low.startswith("unlink ") or low.startswith("delink "):
        # strip first word
        rest = raw.split(maxsplit=1)
        return _unlink(world, rest[1] if len(rest) > 1 else "")
    if "->" not in raw:
        return fmt.hint(
            "Usage: link <exit> -> <place> [type] [both]\n"
            "       link rename <old> as <new>\n"
            "       unlink <exit> [both]"
        )
    left, right = raw.split("->", 1)
    label = left.strip()
    rest = right.strip().split()
    if not label or not rest:
        return fmt.hint("Usage: link <exit label> -> <place name> [type] [both]")
    name_parts: list[str] = []
    link_type = "spatial"
    both = False
    for tok in rest:
        tlow = tok.lower()
        if tlow in LINK_TYPES:
            link_type = tlow
        elif tlow == "both":
            both = True
        else:
            name_parts.append(tok)
    place_name = " ".join(name_parts)
    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")
    matches = world.find_instances_by_name(place_name, kind="place")
    if not matches:
        return fmt.err(f"No place instance matching {place_name!r}.")
    if len(matches) > 1:
        others = [m for m in matches if m.id != loc.id]
        if len(others) == 1:
            matches = others
        else:
            return fmt.err("Ambiguous place name; refine it.")
    dest = matches[0]
    link_ids = world.link(loc.id, dest.id, label, link_type, bidirectional=both)
    world.undo_stack.push(
        f"link {label}",
        lambda w, ids=list(link_ids): w.delete_links(ids),
    )
    extra = " · bidirectional" if both else ""
    return fmt.ok(f"Linked · {label} ({link_type}) → {dest.name}{extra}")


def _parse_both_flag(arg: str) -> tuple[str, bool]:
    """Strip trailing `both` token from an exit-label argument."""
    parts = arg.strip().split()
    if not parts:
        return "", False
    if parts[-1].lower() == "both":
        return " ".join(parts[:-1]).strip(), True
    return arg.strip(), False


def _unlink(world: World, arg: str) -> str:
    """
    Remove an exit from the current place.
    unlink <exit label> [both]
    """
    label_arg, both = _parse_both_flag(arg)
    if not label_arg:
        return fmt.hint(
            "Usage: unlink <exit label> [both]\n"
            "  both  also remove the reverse exit back here (same label, or sole reverse)"
        )
    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")
    ex = world.find_exit(loc.id, label_arg)
    if ex is None:
        return fmt.err(f"No path matching {label_arg!r} from here.  Try: paths")
    snaps: list[dict] = []
    snap = world.link_snapshot(ex["id"])
    if snap:
        snaps.append(snap)
    dest_id = ex["to_instance_id"]
    dest = world.get_instance(dest_id)
    dest_name = dest.name if dest else "?"
    reverse_note = ""

    if both:
        revs = world.reverse_exits(loc.id, dest_id)
        rev = None
        label_l = ex["label"].lower()
        same = [r for r in revs if (r["label"] or "").lower() == label_l]
        if same:
            rev = same[0]
        elif len(revs) == 1:
            rev = revs[0]
        if rev is not None and rev["id"] != ex["id"]:
            rsnap = world.link_snapshot(rev["id"])
            if rsnap:
                snaps.append(rsnap)
            reverse_note = f" · reverse {rev['label']!r}"
        else:
            reverse_note = " · (no reverse exit found)"

    ids = [s["id"] for s in snaps]
    world.delete_links(ids)

    def undo_unlink(w: World, snapshots: list[dict] = list(snaps)) -> None:
        w.restore_links(snapshots)

    world.undo_stack.push(f"unlink {ex['label']}", undo_unlink)
    return fmt.ok(
        f"Unlinked · {ex['label']} → {dest_name}{reverse_note}"
    )


def _link_rename(world: World, arg: str) -> str:
    """
    Rename an exit label from the current place.
    link rename <old> as <new>
    """
    m = re.search(r"\bas\b", arg, flags=re.IGNORECASE)
    if not m:
        return fmt.hint("Usage: link rename <old exit> as <new exit>")
    old_label = arg[: m.start()].strip()
    new_label = arg[m.end() :].strip()
    if not old_label or not new_label:
        return fmt.hint("Usage: link rename <old exit> as <new exit>")
    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")
    ex = world.find_exit(loc.id, old_label)
    if ex is None:
        return fmt.err(f"No path matching {old_label!r} from here.  Try: paths")
    # Exact collision on new label (ignore if renaming same exit to itself via partial)
    existing = None
    for e in world.exits(loc.id):
        if e["label"].lower() == new_label.lower() and e["id"] != ex["id"]:
            existing = e
            break
    if existing is not None:
        return fmt.err(f"Exit {new_label!r} already exists from here.")
    old_exact = ex["label"]
    link_id = ex["id"]
    world.set_link_label(link_id, new_label)

    def undo_rename(w: World, lid: str = link_id, prior: str = old_exact) -> None:
        w.set_link_label(lid, prior)

    world.undo_stack.push(f"link rename {old_exact} → {new_label}", undo_rename)
    dest = world.get_instance(ex["to_instance_id"])
    dest_name = dest.name if dest else "?"
    return fmt.ok(f"Exit renamed · {old_exact} → {new_label}  ({dest_name})")


def _apply_desc_payload(
    world: World,
    target: InstanceView,
    raw: str,
    *,
    label: str,
) -> str:
    """
    Apply show/set/append/clear description payload to ``target`` instance.

    ``raw`` empty → show. Supports clear, +, ++, add, set. Undo pushed.
    """
    tid = target.id
    tname = display_name(target.name)
    ref = world.short_ref_of(tid)

    if not raw:
        body = (target.description or "").strip()
        shown = fmt.prose(body) if body else fmt.hint("(no description)")
        ov = world.get_description_override(tid)
        source = "instance override" if ov is not None else "VEN default"
        return fmt.join_blocks(
            fmt.title_line(f"Description · {fmt.named_ref(tname, ref)}"),
            shown,
            fmt.hint(
                f"{source}  ·  @desc on <match> <text>  ·  "
                f"@desc on <match> +/++/clear  ·  \\n for line breaks"
            ),
            gap=1,
        )

    prior = world.get_description_override(tid)

    if raw.lower() == "clear":
        world.set_description(tid, None)
        world.undo_stack.push(
            f"@desc clear {label}",
            lambda w, iid=tid, p=prior: w.set_description(iid, p),
        )
        return fmt.ok(
            f"Description override cleared · {fmt.named_ref(tname, ref)}  "
            f"(VEN default shows again)"
        )

    from .studio_text import (
        is_studio,
        peel_studio_prefix,
        prepare_stored_text,
        strip_studio_header,
        with_studio_header,
    )

    mode = "set"
    text = raw
    low = raw.lower()
    if low.startswith("++ ") or raw.startswith("++ "):
        mode = "para"
        text = raw[3:].strip()
    elif low.startswith("add "):
        mode = "append"
        text = raw[4:].strip()
    elif raw.startswith("+ ") or (raw.startswith("+") and not raw.startswith("++")):
        mode = "append"
        text = raw[1:].lstrip()

    if not text and mode != "set":
        return fmt.hint(
            f"Usage: @desc on {label} + <text>  ·  @desc on {label} ++ <text>"
        )

    want_studio, text = peel_studio_prefix(text)
    text = unescape_desc(text)
    # Fresh view for append base (override or VEN)
    fresh = world.get_instance(tid)
    effective = (fresh.description if fresh else target.description) or ""
    base_stored = prior if prior is not None else effective
    base_is_studio = is_studio(base_stored) if base_stored else False

    if mode == "set":
        new_desc = prepare_stored_text(text, studio=want_studio)
        msg = f"Description updated · {fmt.named_ref(tname, ref)}"
        if want_studio or is_studio(new_desc):
            msg += "  ·  studio text"
    else:
        if not (base_stored or "").strip():
            new_desc = prepare_stored_text(text, studio=want_studio or base_is_studio)
        elif base_is_studio or want_studio:
            base_body = strip_studio_header(base_stored)
            gap = "\n\n" if mode == "para" else "\n"
            new_desc = with_studio_header(base_body.rstrip() + gap + text)
        else:
            if mode == "para":
                new_desc = base_stored.rstrip() + "\n\n" + text
            else:
                new_desc = base_stored.rstrip() + "\n" + text
        msg = f"Description appended · {fmt.named_ref(tname, ref)}"
        if is_studio(new_desc):
            msg += "  ·  studio text"

    world.set_description(tid, new_desc)
    world.undo_stack.push(
        f"@desc {label}",
        lambda w, iid=tid, p=prior: w.set_description(iid, p),
    )
    return fmt.ok(msg)


def _desc_commit(
    world: World,
    target: InstanceView,
    *,
    story_when: str,
    node_index: int | None,
    lore_title: str = "description update",
) -> str:
    """
    Snapshot current description into material history (+ text log + lore).

    Edits stay free; only commit stamps life-of-item history.
    *lore_title* labels the lore entry (default ``description update``).
    """
    from .studio_text import is_studio, strip_studio_header

    tid = target.id
    tname = display_name(target.name)
    ref = world.short_ref_of(tid)
    body = target.description if target.description is not None else ""
    plain_body = strip_studio_header(body) if is_studio(body) else body
    plain_body = (plain_body or "").strip()
    nlines = len(plain_body.splitlines()) if plain_body else 0
    nchars = len(plain_body)
    first = plain_body.splitlines()[0].strip() if plain_body else ""
    if len(first) > 48:
        first = first[:45] + "…"
    preview = first or "(empty)"
    note = f"{nlines} line(s) · {nchars} ch · {preview}"
    lore_title = (lore_title or "").strip() or "description update"

    # Full body in text revisions so commit is restorable via text show/restore
    from .studio_text import detect_format

    fmt_name, _ = detect_format(body) if body else ("plain", "")
    world.add_text_revision(
        "instance",
        tid,
        body if body is not None else "",
        field="description",
        title=tname,
        format=fmt_name if fmt_name in ("plain", "studio") else "plain",
        author="builder",
        note=f"@desc commit story {story_when}",
    )

    # Readable copy in lore (instance lore list) — plain text, not studio chrome
    lore_id: str | None = None
    if plain_body:
        when_label = (
            story_when
            if story_when and story_when != "@unknown"
            else None
        )
        lore_id = world.add_lore(
            "instance",
            tid,
            body=plain_body,
            title=lore_title,
            timeline_instance_id=target.timeline_instance_id,
            when_label=when_label,
            author="builder",
        )
        # Lore life-row (same story when); separate HST from desc act
        _record_subject_history(
            world,
            "lore",
            lore_id,
            verb="lore",
            story_when=story_when,
            node_index=node_index,
            note=lore_title,
            realm_instance_id=target.realm_instance_id,
            timeline_instance_id=target.timeline_instance_id,
        )

    event_code = _record_subject_history(
        world,
        "instance",
        tid,
        verb="desc",
        story_when=story_when,
        node_index=node_index,
        note=note if not lore_id else f"{note}  ·  lore {lore_id}",
    )
    bits = [
        f"Desc committed · {fmt.named_ref(tname, ref)}",
        f"story {story_when}",
        event_code,
        f"{nlines} line(s)",
    ]
    if lore_id:
        bits.append(f"lore {lore_id}")
        bits.append(f"title {lore_title}")
    return fmt.ok("  ·  ".join(bits))


def _desc(world: World, arg: str) -> str:
    """
    @desc                  — show current place description
    @desc <text>           — replace place (\\n for line breaks)
    @desc + / ++ / clear   — append / clear place override
    @desc commit [when @N] [-t title] — stamp desc into history + lore

    Any instance (no elevate required):
    @desc on <match>              — show that instance's description
    @desc on <match> <text>       — set override on that instance
    @desc on <match> + / ++ / clear
    @desc commit on <match> [when @N] [-t title]
    """
    from .argflags import (
        DESC_COMMIT_FLAG_ALIASES,
        looks_like_flag_command,
        parse_named_flags,
        story_when_from_flag,
    )
    from .story_when import peel_when_anywhere

    raw = arg.strip()

    # ── commit current face into history (edit freely, then commit) ─────
    low = raw.lower()
    if low == "commit" or low.startswith("commit "):
        rest = raw[6:].strip() if low.startswith("commit") else ""
        rest, story_when, node_index = peel_when_anywhere(rest)
        lore_title = "description update"
        target: InstanceView | None = None

        rest_low = rest.lower()
        if rest_low.startswith("on "):
            thing, more, err = _split_instance_target_and_rest(world, rest[3:])
            if err or thing is None:
                return err or fmt.hint(
                    "Usage: @desc commit on <item|person|place> "
                    "[-t title] [when @N]"
                )
            target = thing
            rest = (more or "").strip()

        if rest and (
            looks_like_flag_command(rest)
            or rest.lower().startswith("on ")
        ):
            # flags after on-target, or --on / -t without prose on
            if rest.lower().startswith("on ") and target is None:
                thing, more, err = _split_instance_target_and_rest(
                    world, rest[3:]
                )
                if err or thing is None:
                    return err or fmt.hint(
                        "Usage: @desc commit on <match> [-t title]"
                    )
                target = thing
                rest = (more or "").strip()
            if rest:
                parsed = parse_named_flags(
                    rest, aliases=DESC_COMMIT_FLAG_ALIASES
                )
                if parsed.error:
                    return fmt.err(parsed.error)
                if parsed.get("name"):
                    lore_title = parsed.get("name")
                if "when" in parsed.flags:
                    story_when, node_index = story_when_from_flag(
                        parsed.get("when")
                    )
                if parsed.get("on") and target is None:
                    thing, err = _resolve_instance_target(
                        world, parsed.get("on")
                    )
                    if err or thing is None:
                        return err or fmt.err(
                            f"No match for {parsed.get('on')!r}."
                        )
                    target = thing
                if parsed.positionals:
                    return fmt.hint(
                        "Usage: @desc commit [-t title] [when @N]  ·  "
                        "@desc commit on <match> -t Soft dusk when @1\n"
                        "  Default lore title: description update"
                    )
        elif rest:
            return fmt.hint(
                "Usage: @desc commit [-t title] [when @N]  ·  "
                "@desc commit on <match> [-t title] [when @N]\n"
                "  Default lore title: description update"
            )

        if target is None:
            loc = world.player_location()
            if not loc:
                return fmt.hint("Nowhere.")
            target = loc
        return _desc_commit(
            world,
            target,
            story_when=story_when,
            node_index=node_index,
            lore_title=lore_title,
        )

    # ── instance target ─────────────────────────────────────────────────
    if raw.lower().startswith("on "):
        thing, rest, err = _split_instance_target_and_rest(world, raw[3:])
        if err or thing is None:
            return err or fmt.hint(
                "Usage: @desc on <item|person|place match> [text|+|++|clear]"
            )
        return _apply_desc_payload(world, thing, rest, label=thing.name)

    # ── current place (default) ─────────────────────────────────────────
    loc = world.player_location()
    if not loc:
        return fmt.hint("Nowhere.")

    if not raw:
        body = loc.description.strip()
        shown = fmt.prose(body) if body else fmt.hint("(no description)")
        return fmt.join_blocks(
            fmt.title_line(f"Description · {loc.name}"),
            shown,
            fmt.hint(
                "@desc <text>  ·  @desc studio | **bold**  ·  "
                "@desc + / ++ / clear  ·  @desc commit  ·  "
                "@desc on <item> …  ·  @desc <<studio  ·  help studio-text"
            ),
            gap=1,
        )

    return _apply_desc_payload(world, loc, raw, label="here")


def _undo(world: World) -> str:
    try:
        summary = world.undo_stack.undo(world)
    except ValueError as e:
        return fmt.hint(str(e))
    return fmt.ok(f"Undone · {summary}")


def _text_cmd(world: World, arg: str) -> str:
    """
    text log [desc|on <m>|book <m> [page n]|lore]
    text show <revision-id>
    text restore <revision-id>
    """
    raw = (arg or "").strip()
    if not raw:
        return fmt.hint(
            "Usage: text log [desc | on <item> | book <name> [page n] | lore]  ·  "
            "text show <id>  ·  text restore <id>\n"
            "  Editor saves (<< / <<studio) append to this log."
        )
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("log", "history", "list", "ls"):
        return _text_log(world, rest)
    if sub in ("show", "view", "get"):
        if not rest:
            return fmt.hint("Usage: text show <revision-id>")
        return _text_show(world, rest)
    if sub in ("restore", "revert", "checkout"):
        if not rest:
            return fmt.hint("Usage: text restore <revision-id>")
        return _text_restore(world, rest)
    return fmt.hint(
        "Usage: text log …  ·  text show <id>  ·  text restore <id>"
    )


def _text_log(world: World, rest: str) -> str:
    subject_type, subject_id, field, label = _resolve_text_log_target(world, rest)
    if subject_id is None:
        return label  # error/hint already
    rows = world.list_text_revisions(subject_type, subject_id, field=field)
    if not rows:
        return fmt.hint(f"No editor saves yet for {label}.  Use << or <<studio.")
    lines = [
        fmt.title_line(f"Text log · {label}"),
        fmt.hint("text show <id>  ·  text restore <id>"),
        "",
    ]
    for r in rows:
        rid = r["id"]
        short = rid if len(rid) <= 16 else rid[:14] + "…"
        first = (r["body"] or "").strip().splitlines()
        preview = first[0][:48] if first else "(empty)"
        nlines = len((r["body"] or "").splitlines()) or 0
        when = r["created_at"] or ""
        lines.append(
            f"  [bold {fmt.ACCENT}]{fmt.safe(short)}[/bold {fmt.ACCENT}]  "
            f"[dim]{fmt.safe(when)}[/dim]  "
            f"{fmt.safe(r['format'])}  {nlines} lines"
        )
        lines.append(f"      [dim]{fmt.safe(preview)}[/dim]")
    return "\n".join(lines)


def _resolve_text_log_target(
    world: World, rest: str
) -> tuple[str, str | None, str | None, str]:
    """Return (subject_type, subject_id|None, field|None, label_or_error)."""
    raw = (rest or "").strip()
    if not raw or raw.lower() in ("desc", "here", "place"):
        loc = world.player_location()
        if not loc:
            return "instance", None, None, fmt.hint("Nowhere.")
        return (
            "instance",
            loc.id,
            "description",
            f"desc · {display_name(loc.name)}",
        )
    low = raw.lower()
    if low.startswith("on "):
        thing = world.resolve_here_named(raw[3:].strip())
        if not thing:
            return "instance", None, None, fmt.err(f"No {raw[3:].strip()!r} here.")
        return (
            "instance",
            thing.id,
            "description",
            f"desc · {display_name(thing.name)}",
        )
    if low.startswith("book ") or low.startswith("folio "):
        tail = raw.split(maxsplit=1)[1].strip() if " " in raw else ""
        page_n = None
        m = re.search(r"\b(?:page|leaf)\s+(\d+)\s*$", tail, flags=re.I)
        if m:
            page_n = int(m.group(1))
            tail = tail[: m.start()].strip()
        book, err = _resolve_book_here(world, tail)
        if err or book is None:
            return "book_page", None, None, err or fmt.err("No folio.")
        pages = world.list_book_pages(book.id)
        if not pages:
            return "book_page", None, None, fmt.hint("Folio has no leaves yet.")
        if page_n is None:
            page_n = 1
        try:
            page = world._book_page_row(book.id, page_n)
        except Exception as e:  # noqa: BLE001
            return "book_page", None, None, fmt.err(str(e))
        return (
            "book_page",
            page["id"],
            "body",
            f"book · {display_name(book.name)} p{page_n}",
        )
    if low.startswith("lore"):
        rest2 = raw[4:].strip()
        if rest2.lower().startswith("on "):
            thing = world.resolve_here_named(rest2[3:].strip())
            if not thing:
                return "instance", None, None, fmt.err(f"No match {rest2[3:]!r}.")
            return (
                "instance",
                thing.id,
                "lore_body",
                f"lore · {display_name(thing.name)}",
            )
        loc = world.player_location()
        if not loc:
            return "instance", None, None, fmt.hint("Nowhere.")
        return (
            "instance",
            loc.id,
            "lore_body",
            f"lore · {display_name(loc.name)}",
        )
    thing = world.resolve_here_named(raw)
    if thing:
        return (
            "instance",
            thing.id,
            "description",
            f"desc · {display_name(thing.name)}",
        )
    return (
        "instance",
        None,
        None,
        fmt.hint(
            "Usage: text log  ·  text log on <item>  ·  "
            "text log book <name> [page n]  ·  text log lore"
        ),
    )


def _text_show(world: World, rev_q: str) -> str:
    row = world.find_text_revision(rev_q)
    if row is None:
        return fmt.err(f"No text revision matching {rev_q!r}.")
    body = row["body"] or ""
    lines = [
        fmt.title_line(f"Text revision · {row['id']}"),
        fmt.hint(
            f"{row['subject_type']}/{row['field']}  ·  {row['format']}  ·  "
            f"{row['created_at']}"
        ),
        "",
        fmt.prose(body) if body.strip() else fmt.hint("(empty)"),
    ]
    return "\n".join(lines)


def _text_restore(world: World, rev_q: str) -> str:
    row = world.find_text_revision(rev_q)
    if row is None:
        return fmt.err(f"No text revision matching {rev_q!r}.")
    body = row["body"] or ""
    st = row["subject_type"]
    sid = row["subject_id"]
    field = row["field"] or "body"
    note = f"restored from {row['id']}"

    if st == "instance" and field == "description":
        prior = world.get_description_override(sid)
        world.set_description(sid, body)
        world.undo_stack.push(
            f"text restore {row['id']}",
            lambda w, iid=sid, p=prior: w.set_description(iid, p),
        )
        world.add_text_revision(
            st, sid, body, field=field, format=row["format"] or "plain", note=note
        )
        inst = world.get_instance(sid)
        name = display_name(inst.name) if inst else sid
        return fmt.ok(f"Restored description · {name}  from  {row['id']}")

    if st == "book_page" and field == "body":
        page = world.conn.execute(
            "SELECT * FROM book_pages WHERE id = ?", (sid,)
        ).fetchone()
        if page is None:
            return fmt.err("Book page no longer exists.")
        prior_body = page["body"]
        world._update_book_page_body(sid, body)
        book_id = page["book_instance_id"]
        pos = page["position"]

        def _undo_page(w, bid=book_id, p=pos, old=prior_body):
            w.set_book_page_body(bid, p, old)

        world.undo_stack.push(f"text restore {row['id']}", _undo_page)
        world.add_text_revision(
            st,
            sid,
            body,
            field=field,
            title=page["title"] or "",
            format=row["format"] or "plain",
            note=note,
        )
        return fmt.ok(f"Restored book page body  from  {row['id']}")

    if field == "lore_body":
        lid = world.add_lore(
            "ven" if st == "ven" else "instance",
            sid,
            body=body,
            title=row["title"] or "Restored",
            author="builder",
        )
        world.undo_stack.push(
            f"text restore lore {row['id']}",
            lambda w, x=lid: w.delete_lore(x),
        )
        world.add_text_revision(
            st,
            sid,
            body,
            field=field,
            title=row["title"] or "",
            format=row["format"] or "plain",
            note=note,
        )
        return fmt.ok(f"Restored lore as new entry · {lid}  from  {row['id']}")

    return fmt.err(f"Cannot restore {st}/{field}.")


def _history(world: World, arg: str) -> str:
    """
    history                  — usage
    history nodes            — nodes on current place timeline
    history here             — history for this place instance
    history me / builder     — history for the player instance
    history on <match>       — history for an instance
    history ven <match>      — history for a prime VEN
    history event HST-001    — all legs of one shared event
    history HST-001          — same as event
    """
    from .story_when import format_history_line
    from .ids import display_name as dname, parse_history_event_code

    arg = (arg or "").strip()
    low = arg.lower()

    if not arg:
        return fmt.hint(
            "Usage: history nodes  ·  history here  ·  history me  ·  "
            "history on <thing>  ·  history ven <prime>  ·  history HST-001\n"
            "  Shared event codes (HST-NNN) link put/receive, take/give, etc.\n"
            "  Story when:  … when @3  ·  --when 0  ·  default @unknown"
        )

    if low in ("nodes", "node"):
        loc = world.player_location()
        if not loc or not loc.timeline_instance_id:
            return fmt.hint("No timeline on this place.  timeline set <name>")
        tl = world.get_instance(loc.timeline_instance_id)
        nodes = world.list_timeline_nodes(loc.timeline_instance_id)
        title = dname(tl.name) if tl else "timeline"
        if not nodes:
            return fmt.join_blocks(
                fmt.section(f"Nodes · {title}"),
                fmt.hint(
                    "None yet.  create/spawn … when @0  ensures node 0 "
                    "(and higher N as used)."
                ),
                gap=0,
            )
        lines = [fmt.section(f"Nodes · {title}")]
        for n in nodes:
            nm = (n["name"] or "").strip()
            label = f"@{n['node_index']}"
            if nm:
                label = f"{label}  {nm}"
            lines.append(fmt.bullet(label, n["created_at"] or ""))
        return "\n".join(lines)

    def _where_names(row) -> tuple[str | None, str | None, str | None]:
        """Prefer snapshotted names; fall back to live instance titles."""
        keys = set(row.keys()) if hasattr(row, "keys") else set()

        def snap(col: str, iid_col: str) -> str | None:
            if col in keys:
                s = (row[col] or "").strip()
                if s:
                    return s
            iid = row[iid_col] if iid_col in keys else None
            if iid:
                inst = world.get_instance(iid)
                if inst:
                    return dname(inst.name)
            return None

        return (
            snap("place_name", "place_instance_id"),
            snap("realm_name", "realm_instance_id"),
            snap("timeline_name", "timeline_instance_id"),
        )

    def _subject_label(subject_type: str, subject_id: str) -> str:
        if subject_type == "instance":
            inst = world.get_instance(subject_id)
            if inst:
                ref = world.short_ref_of(inst.id)
                return fmt.named_ref(inst.name, ref)
            return subject_id
        if subject_type == "ven":
            ven = world.get_ven(subject_id)
            if ven:
                return f"{ven.name} [{ven.slug}]"
            return subject_id
        return f"{subject_type}:{subject_id}"

    def _format_entries(
        heading: str, rows: list, *, show_subject: bool = False
    ) -> str:
        if not rows:
            return fmt.join_blocks(
                fmt.section(heading),
                fmt.hint("No history entries yet."),
                gap=0,
            )
        lines = [fmt.section(heading)]
        for r in rows:
            pn, rn, tn = _where_names(r)
            note = r["note"] or ""
            if show_subject:
                sub = _subject_label(
                    r["subject_type"] or "instance", r["subject_id"] or ""
                )
                note = f"{sub}  ·  {note}" if note else sub
            block = format_history_line(
                verb=r["verb"] or "record",
                story_when=r["story_when"] or "@unknown",
                crafted_at=r["created_at"] or "—",
                place_name=pn,
                realm_name=rn,
                timeline_name=tn,
                note=note,
                event_code=r["event_code"] or "",
            )
            # Two lines: what happened · dimmed when/where (indented for lists)
            primary, _, meta = block.partition("\n")
            lines.append(f"  {primary}")
            if meta:
                lines.append(f"    {fmt.hint(meta)}")
        return "\n".join(lines)

    # Shared event lookup: history HST-001 · history event HST-001
    event_raw = arg
    if low.startswith("event "):
        event_raw = arg[6:].strip()
    event_code = parse_history_event_code(event_raw)
    if event_code:
        rows = world.history_for_event(event_code)
        return _format_entries(
            f"History event · {event_code}",
            rows,
            show_subject=True,
        )

    if low in ("me", "self", "i", "player") or low.startswith("me "):
        player = _player_instance(world)
        if not player:
            return fmt.hint("No player set.")
        rows = world.history_for("instance", player.id)
        ref = world.short_ref_of(player.id)
        return _format_entries(
            f"History · {fmt.named_ref(player.name, ref)} (you)", rows
        )

    if low == "here" or low.startswith("here "):
        loc = world.player_location()
        if not loc:
            return fmt.hint("Nowhere.")
        rows = world.history_for("instance", loc.id)
        return _format_entries(
            f"History · {dname(loc.name)} (place)", rows
        )

    if low.startswith("ven "):
        target = arg[4:].strip()
        ven = world.find_ven(target)
        if not ven:
            return fmt.err(f"No VEN matching {target!r}.")
        rows = world.history_for("ven", ven.id)
        return _format_entries(f"History · {ven.name} [{ven.slug}]", rows)

    if low.startswith("on "):
        target = arg[3:].strip()
        thing, err = _resolve_instance_target(world, target)
        if err or thing is None:
            return err or fmt.err(f"No match for {target!r}.")
        rows = world.history_for("instance", thing.id)
        ref = world.short_ref_of(thing.id)
        return _format_entries(
            f"History · {fmt.named_ref(thing.name, ref)}", rows
        )

    thing, err = _resolve_instance_target(world, arg)
    if thing is not None:
        rows = world.history_for("instance", thing.id)
        ref = world.short_ref_of(thing.id)
        return _format_entries(
            f"History · {fmt.named_ref(thing.name, ref)}", rows
        )
    ven = world.find_ven(arg)
    if ven is not None:
        rows = world.history_for("ven", ven.id)
        return _format_entries(f"History · {ven.name} [{ven.slug}]", rows)
    return fmt.err(
        f"No history subject matching {arg!r}.  "
        f"Try: history on <thing>  ·  history me  ·  history here  ·  "
        f"history HST-001"
    )


def _retime(world: World, arg: str) -> str:
    """
    retime HST-003 when @2
    retime #HST-003 --when 0
    retime HST-003 @unknown
    retime HST-003 unknown

    Rewrite story_when on every leg of a shared history event.
    """
    from .argflags import story_when_from_flag
    from .ids import parse_history_event_code
    from .story_when import peel_when_anywhere

    raw = (arg or "").strip()
    if not raw:
        return fmt.hint(
            "Usage: retime <HST-NNN> when @N  ·  retime HST-003 --when 2\n"
            "  retime #HST-001 @unknown  ·  retime HST-001 unknown\n"
            "  Updates every leg of that event (thing + vessel + you + place)."
        )

    rest, sw_peel, ni_peel = peel_when_anywhere(raw)
    tokens = rest.split()
    if not tokens:
        return fmt.hint("Usage: retime <HST-NNN> when @N")

    code_tok = tokens[0].lstrip("#")
    code = parse_history_event_code(code_tok)
    if not code:
        return fmt.err(
            f"Need a history event code (HST-001), got {tokens[0]!r}.\n"
            + fmt.hint("List: history on <thing>  ·  history HST-001")
        )

    story_when = sw_peel
    node_index = ni_peel
    # Bare stamp after the code: retime HST-003 @2 | retime HST-003 2 | unknown
    if story_when == "@unknown" and node_index is None and len(tokens) >= 2:
        stamp = " ".join(tokens[1:]).strip()
        story_when, node_index = story_when_from_flag(stamp)
    elif story_when == "@unknown" and node_index is None and len(tokens) == 1:
        return fmt.hint(
            f"Usage: retime {code} when @N  ·  retime {code} --when 0  ·  "
            f"retime {code} @unknown"
        )

    try:
        code, n, prior = world.retime_history_event(
            code, story_when=story_when, node_index=node_index
        )
    except ValueError as e:
        return fmt.err(str(e))

    def undo_retime(w: World, priors: list[dict] = prior) -> None:
        w.restore_history_event_times(priors)

    old = prior[0]["story_when"] if prior else "?"
    world.undo_stack.push(f"retime {code}", undo_retime)
    rows = world.history_for_event(code)
    new_sw = (rows[0]["story_when"] if rows else story_when) or story_when
    return fmt.ok(
        f"Retimed · {code}  ·  {old} → {new_sw}  ·  {n} leg(s)  ·  undo"
    )


def _parse_create_of(
    world: World, rest: str
) -> tuple[str, str, str | None]:
    """
    Parse name [| description] [of parent] from create rest.

    Parent: trailing `` of <parent>`` on the name side (before ``|``) when
    *parent* resolves to an existing VEN **and** the child name is multi-word
    (contains a space). That avoids eating titles like ``Concept of Him``
    (single-word head + ``of`` + word).

    Quoted names work without that multi-word rule::

        create concept "Concept of Him" | …
        create object "Document" of File | …
    """
    parent_query: str | None = None
    if "|" in rest:
        name_side, desc = rest.split("|", 1)
        name_side, desc = name_side.strip(), desc.strip()
    else:
        name_side, desc = rest.strip(), ""

    # Strip matching quotes around the whole name side (optional)
    quoted = False
    if len(name_side) >= 2 and name_side[0] == name_side[-1] and name_side[0] in "\"'":
        name_side = name_side[1:-1].strip()
        quoted = True
    # name "Child" of Parent (quotes only around child)
    if not quoted and " of " in name_side.lower():
        # try: "Child Name" of Parent
        for q in ('"', "'"):
            if name_side.startswith(q) and f"{q} of " in name_side.lower():
                # find closing quote before of
                end = name_side.find(q, 1)
                if end > 0:
                    after = name_side[end + 1 :].strip()
                    if after.lower().startswith("of "):
                        child = name_side[1:end].strip()
                        parent = after[3:].strip()
                        if child and parent and world.find_ven(parent) is not None:
                            return child, desc, parent
                break

    lower = name_side.lower()
    idx = lower.rfind(" of ")
    if idx >= 0:
        maybe_name = name_side[:idx].strip()
        maybe_parent = name_side[idx + 4 :].strip()
        if (
            maybe_name
            and maybe_parent
            and world.find_ven(maybe_parent) is not None
            and (" " in maybe_name or quoted)
        ):
            name_side = maybe_name
            parent_query = maybe_parent
    return name_side, desc, parent_query


def _print_usage() -> str:
    return (
        "Usage:\n"
        "  print ticket -t date -k range -n Global Release Date "
        "-d Jan 20 - Feb 15 2026\n"
        "\n"
        "Prints a Temporary Data Fragment (TDF) — a movable ticket slip.\n"
        "  -t / --subtype   ticket subtype (date for calendars; also label, note)\n"
        "  -k / --kind      range | due | state | point\n"
        "  -n / --name      title on the slip\n"
        "  -d / --desc      body / date range text (bare - in ranges is ok)\n"
        "\n"
        "Slips land in the current place; take / put / look work like other things.\n"
        "Id shape: TDF-######## (not a full VEN prime per slip)."
    )


def _print_cmd(world: World, arg: str) -> str:
    """print ticket … — receipt-style TDF slips for offices/calendars."""
    raw = (arg or "").strip()
    if not raw:
        return fmt.hint(_print_usage())
    parts = raw.split(maxsplit=1)
    what = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""
    if what in ("ticket", "tdf", "slip", "tag"):
        return _print_ticket(world, rest)
    return fmt.hint(
        f"Unknown print target {what!r}.\n" + _print_usage()
    )


# print ticket flags: -t is subtype (date), not create's type
_PRINT_TICKET_FLAG_ALIASES: dict[str, str] = {
    "t": "subtype",
    "subtype": "subtype",
    "type": "subtype",
    "k": "kind",
    "kind": "kind",
    "n": "name",
    "name": "name",
    "title": "name",
    "d": "desc",
    "desc": "desc",
    "description": "desc",
    "body": "desc",
    "b": "desc",
}


def _print_ticket(world: World, arg: str) -> str:
    from .argflags import parse_named_flags
    from .tdf import TICKET_KINDS, TICKET_SUBTYPES

    arg = (arg or "").strip()
    if not arg:
        return fmt.hint(_print_usage())

    parsed = parse_named_flags(arg, aliases=_PRINT_TICKET_FLAG_ALIASES)
    if parsed.error:
        return fmt.err(parsed.error)

    subtype = parsed.get("subtype") or "date"
    kind = parsed.get("kind") or "range"
    name = parsed.get("name")
    desc = parsed.get("desc")

    # Recover range text after bare "-" tokens (shlex splits them out of -d)
    if parsed.positionals:
        extra = " ".join(parsed.positionals)
        if desc:
            desc = f"{desc} {extra}".strip()
        elif not name and len(parsed.positionals) >= 1:
            # no -n: treat leading positionals as name if we still need one
            name = extra
        else:
            desc = (desc + " " + extra).strip() if desc else extra

    if not name:
        return fmt.hint(
            "print ticket needs -n / --name\n" + _print_usage()
        )

    subtype_l = subtype.lower().strip()
    kind_l = kind.lower().strip()
    # Soft allow unknown subtypes/kinds (office vocabulary will grow)
    if subtype_l not in TICKET_SUBTYPES and subtype_l:
        pass  # allow custom
    if kind_l not in TICKET_KINDS and kind_l:
        pass

    try:
        inst_id, code = world.print_ticket(
            name=name,
            subtype=subtype_l,
            kind=kind_l,
            description=desc or "",
        )
    except ValueError as e:
        return fmt.err(str(e))

    inst = world.get_instance(inst_id)
    assert inst is not None
    payload = world.tdf_payload(inst_id) or {}
    data = payload.get("data") or {}
    start = (data.get("start") or "").strip()
    end = (data.get("end") or "").strip()
    range_bit = ""
    if start and end:
        range_bit = f"{start} → {end}"
    elif start:
        range_bit = start
    elif data.get("raw"):
        range_bit = str(data.get("raw"))

    world.undo_stack.push(
        f"print ticket {code}",
        lambda w, iid=inst_id: w.delete_instance(iid),
    )

    lines = [
        fmt.ok(f"Printed ticket · {inst.name}"),
        fmt.hint(
            f"  {code}  ·  type ticket  ·  subtype {subtype_l}  ·  kind {kind_l}"
        ),
    ]
    if range_bit:
        lines.append(fmt.hint(f"  data  {range_bit}"))
    lines.append(
        fmt.hint(
            f"  TDF slip in place — take / put / examine {code}  ·  examine {inst.name}"
        )
    )
    return fmt.join_blocks(*lines, gap=0)


def _create_usage() -> str:
    return (
        "Usage (flags, free order):\n"
        "  create --type sense/feeling --when 0 --name Satisfaction "
        "--desc The feeling of something working well.\n"
        "  Short: -t -w -n -d  ·  also --kind --description --of Parent\n"
        "Legacy: create <kind>[/subtype] <name> [| desc] [of Parent] [when @N]\n"
        f"Kinds: {', '.join(KINDS)}"
    )


def _create(world: World, arg: str) -> str:
    """
    create --type <kind[/subtype]> --name <title> [--desc …] [--when N] [--of parent]
    create <kind> <name> [| description] [of parent] [when @N]

    Lean roots + free-order flags so type/when/name/desc are not order-fragile.
    """
    from .argflags import (
        looks_like_flag_command,
        parse_named_flags,
        story_when_from_flag,
    )
    from .story_when import peel_story_when_suffix

    arg = (arg or "").strip()
    if not arg:
        return fmt.hint(_create_usage())

    story_when = "@unknown"
    node_index: int | None = None
    kind: str
    subtype: str | None
    name: str
    desc: str
    parent_query: str | None = None

    if looks_like_flag_command(arg):
        parsed = parse_named_flags(arg)
        if parsed.error:
            return fmt.err(parsed.error)
        kind_spec = parsed.get("type")
        name = parsed.get("name")
        desc = parsed.get("desc")
        parent_query = parsed.get("of") or None
        if not kind_spec and parsed.positionals:
            kind_spec = parsed.positionals[0]
        if not name and len(parsed.positionals) >= 2:
            name = " ".join(parsed.positionals[1:])
        elif not name and len(parsed.positionals) == 1 and parsed.get("type"):
            name = parsed.positionals[0]
        if not kind_spec or not name:
            return fmt.hint(_create_usage())
        kind, subtype = parse_kind_spec(kind_spec)
        if "when" in parsed.flags:
            story_when, node_index = story_when_from_flag(parsed.get("when"))
    else:
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            return fmt.hint(_create_usage())
        kind_spec, rest = parts[0], parts[1]
        kind, subtype = parse_kind_spec(kind_spec)
        rest, story_when, node_index = peel_story_when_suffix(rest)
        name, desc, parent_query = _parse_create_of(world, rest)
        if not name:
            return fmt.hint(_create_usage())

    if kind not in KINDS:
        return fmt.err(
            f"Unknown kind {kind!r}.  Try: kinds  ·  "
            f"roots: person place bin thing folio symbol sense event"
        )
    if subtype and kind not in SUBTYPE_KINDS:
        return fmt.err(
            f"Subtype not used on {kind!r}  ·  adventure roots take subtypes."
        )
    parent_ven_id = None
    parent_label = None
    if parent_query:
        parent = world.find_ven(parent_query)
        if parent is None:
            return fmt.err(f"No parent VEN matching {parent_query!r}.")
        parent_ven_id = parent.id
        parent_label = parent.name
    meta = {"subtype": subtype} if subtype else None
    ven_id = world.create_ven(
        name, kind, description=desc, meta=meta, parent_ven_id=parent_ven_id
    )
    world.undo_stack.push(
        f"create {kind}",
        lambda w, vid=ven_id: w.delete_ven(vid),
    )
    from .story_when import resolve_history_where

    where = resolve_history_where(world)
    event_code = world.next_history_event_code()
    world.record_history(
        "ven",
        ven_id,
        verb="create",
        story_when=story_when,
        node_index=node_index,
        place_instance_id=where["place_instance_id"],
        place_name=where["place_name"] or "",
        realm_instance_id=where["realm_instance_id"],
        realm_name=where["realm_name"] or "",
        timeline_instance_id=where["timeline_instance_id"],
        timeline_name=where["timeline_name"] or "",
        note=name,
        event_code=event_code,
    )
    ven = world.get_ven(ven_id)
    assert ven is not None
    label = format_kind_label(ven.kind, ven.subtype)
    code_bit = f"code {ven.code}  ·  " if ven.code else ""
    bits = [
        f"{label}  ·  {code_bit}slug {ven.slug}  ·  {event_code}  ·  {ven.id}"
    ]
    if parent_label:
        bits.append(f"of {parent_label}")
    bits.append(f"story {story_when}")
    return fmt.join_blocks(
        fmt.ok(f"Created prime VEN · {ven.name}"),
        fmt.hint("  ·  ".join(bits)),
        gap=0,
    )


def _spawn_usage() -> str:
    return (
        "Usage (flags, free order):\n"
        "  spawn --ven field-notes -n Ritual Notes --when 2\n"
        "  Short: -n / --name / --title  ·  -w when\n"
        "Prose: spawn <ven> as <title>  ·  spawn <ven> -> <title> [when @N]\n"
        "  Places: create place Room  ·  spawn room -> Kitchen  ·  link …"
    )


def _spawn(world: World, arg: str) -> str:
    """
    spawn --ven <prime> [-n|--name|--title <title>] [--when N]
    spawn <ven> [as|-> <title>] [when @N]

    Things land in the current place. Places spawn free-standing (link after).
    """
    from .argflags import (
        looks_like_flag_command,
        parse_named_flags,
        story_when_from_flag,
    )
    from .story_when import peel_story_when_suffix

    if not arg:
        return fmt.hint(_spawn_usage())

    story_when = "@unknown"
    node_index: int | None = None
    name_override: str | None = None
    target: str

    if looks_like_flag_command(arg):
        parsed = parse_named_flags(arg)
        if parsed.error:
            return fmt.err(parsed.error)
        target = parsed.get("ven")
        # Lived title: -n / --name / --title (not -a — reserved for add)
        name_override = parsed.get("name") or None
        if not target and parsed.positionals:
            target = parsed.positionals[0]
        if not name_override and len(parsed.positionals) >= 2:
            name_override = " ".join(parsed.positionals[1:])
        if not target:
            return fmt.hint(_spawn_usage())
        if "when" in parsed.flags:
            story_when, node_index = story_when_from_flag(parsed.get("when"))
    else:
        arg, story_when, node_index = peel_story_when_suffix(arg)
        name_override = None
        split = split_as_title(arg)
        if split:
            target, name_override = split
        else:
            target = arg.strip()
    ven = world.find_ven(target)
    if not ven:
        return fmt.err(f"No VEN matching {target!r}.")
    loc = world.player_location()

    # Auto-unique title when bare spawn would collide among reachable copies
    if not name_override:
        if ven.kind == "place":
            all_of_ven = world.list_instances_of_ven(ven.id)
            if all_of_ven:
                n = len(all_of_ven) + 1
                name_override = f"{display_name(ven.name)} {n}"
        else:
            existing = [
                c
                for c in world.resolve_here_candidates()
                if c.ven_id == ven.id
            ]
            all_of_ven = world.list_instances_of_ven(ven.id)
            if existing or all_of_ven:
                n = len(all_of_ven) + 1
                name_override = f"{display_name(ven.name)} {n}"

    inst_id = world.instantiate(
        ven.id,
        name_override=name_override,
        realm_instance_id=loc.realm_instance_id if loc else None,
        timeline_instance_id=loc.timeline_instance_id if loc else None,
    )
    # Places are destinations in the multiverse — do not nest them inside "here"
    # (that made Room instances look like floor props, not go-able rooms).
    if ven.kind != "place":
        if loc and ven.kind != "person":
            if is_inner_life_kind(ven.kind, ven.subtype):
                slot = default_inner_slot(ven.kind, ven.subtype)
            else:
                slot = "interior"
            world.put_in(inst_id, loc.id, slot=slot)
        elif loc and ven.kind == "person":
            # person/archetype into a room stays on the floor; into a person is inner
            world.put_in(inst_id, loc.id, slot="interior")

    world.undo_stack.push(
        f"spawn {ven.name}",
        lambda w, iid=inst_id: w.delete_instance(iid),
    )
    inst = world.get_instance(inst_id)
    assert inst is not None
    from .story_when import resolve_history_where

    where = resolve_history_where(
        world,
        place_instance_id=loc.id if loc else None,
        realm_instance_id=inst.realm_instance_id
        or (loc.realm_instance_id if loc else None),
        timeline_instance_id=inst.timeline_instance_id
        or (loc.timeline_instance_id if loc else None),
    )
    # Spawn event: instance always; place also receives floor spawns
    spawn_legs: list[dict] = [
        {
            "subject_type": "instance",
            "subject_id": inst_id,
            "verb": "spawn",
            "note": display_name(inst.name),
        }
    ]
    if loc and ven.kind != "place":
        spawn_legs.append(
            {
                "subject_type": "instance",
                "subject_id": loc.id,
                "verb": "receive",
                "note": f"spawned {display_name(inst.name)} on floor",
            }
        )
    event_code = world.record_history_event(
        spawn_legs,
        story_when=story_when,
        node_index=node_index,
        place_instance_id=where["place_instance_id"],
        place_name=where["place_name"] or "",
        realm_instance_id=where["realm_instance_id"],
        realm_name=where["realm_name"] or "",
        timeline_instance_id=where["timeline_instance_id"],
        timeline_name=where["timeline_name"] or "",
    )
    ref = world.short_ref_of(inst_id)
    label = format_kind_label(ven.kind, ven.subtype)
    prime_bit = ven.code or ven.slug
    if ven.kind == "place":
        title = display_name(inst.name)
        return fmt.join_blocks(
            fmt.ok(f"Spawned place · {fmt.named_ref(title, ref)}"),
            fmt.hint(
                f"{label}  ·  prime {prime_bit}  ·  unlinked room  ·  "
                f"story {story_when}  ·  {event_code}  ·  {inst_id}"
            ),
            fmt.hint(
                f"Link:  link <exit> -> {title} both  ·  "
                f"instances {prime_bit}"
            ),
            gap=0,
        )
    where = world.where_label(inst_id)
    return fmt.join_blocks(
        fmt.ok(f"Spawned · {fmt.named_ref(inst.name, ref)}"),
        fmt.hint(
            f"{label}  ·  prime {prime_bit}  ·  {where}  ·  "
            f"story {story_when}  ·  {event_code}  ·  {inst_id}"
        ),
        gap=0,
    )


def _resolve_rename_target(
    world: World, match: str
) -> tuple[InstanceView | None, str | None]:
    """
    Resolve something to retitle: reachable things, current place, or any place.

    Places are not in room/inventory candidates (you stand *in* them), so
    rename needs special targets: here / place / room, or place-by-name.
    """
    key = match.strip()
    if not key:
        return None, fmt.hint("Usage: rename <thing|here|place name> as <new title>")
    low = key.lower()
    if low in ("here", "place", "room", "this", "location"):
        loc = world.player_location()
        if not loc:
            return None, fmt.hint("Nowhere.")
        return loc, None
    # Player avatar (excluded from normal here-candidates)
    if low in ("me", "self", "player", "you", "builder"):
        pid = world.player_id()
        if not pid:
            return None, fmt.hint("No player avatar set.")
        me = world.get_instance(pid)
        if me is None:
            return None, fmt.hint("No player avatar.")
        return me, None

    # Reachable objects / people / books first
    here_matches = world.resolve_here_matches(key)
    if len(here_matches) == 1:
        return here_matches[0], None
    if len(here_matches) > 1:
        return None, _format_ambiguous(world, key, here_matches)

    # Any place instance (current room or elsewhere)
    places = world.find_instances_by_name(key, kind="place")
    if len(places) == 1:
        return places[0], None
    if len(places) > 1:
        return None, _format_ambiguous(world, key, places)

    return None, fmt.err(
        f"No {key!r} here, in inventory, or as a place.\n"
        + fmt.hint("rename here as …  ·  rename <place name> as …  ·  rename <thing> as …")
    )


def _rename(world: World, arg: str) -> str:
    """rename <match|here|me|place> as|-> <new title> [when @N]  ·  call …"""
    from .story_when import peel_when_anywhere

    usage = (
        "Usage: rename <thing|me|here|place name> as <new title> "
        "[when @N | --when 0]\n"
        "  Also: rename me -> Ada  ·  rename pocket → Travel Notes\n"
        "  Prime: vens rename Builder as Ada"
    )
    if not (arg or "").strip():
        return fmt.hint(usage)
    arg, story_when, node_index = peel_when_anywhere(arg)
    split = split_as_title(arg)
    if not split:
        return fmt.hint(usage)
    match, new_title = split
    thing, err = _resolve_rename_target(world, match)
    if err:
        return err
    assert thing is not None
    prior = thing.name
    prior_override = world.get_name_override(thing.id)
    world.set_name_override(thing.id, new_title)
    iid = thing.id

    def undo_rename(
        w: World, instance_id: str = iid, old: str | None = prior_override
    ) -> None:
        w.set_name_override(instance_id, old)

    world.undo_stack.push(f"rename {display_name(prior)}", undo_rename)
    ref = world.short_ref_of(thing.id)
    updated = world.get_instance(thing.id)
    assert updated is not None
    old_disp = display_name(prior)
    new_disp = display_name(updated.name)
    event_code = _record_subject_history(
        world,
        "instance",
        iid,
        verb="rename",
        story_when=story_when,
        node_index=node_index,
        note=f"{old_disp} → {new_disp}",
    )
    kind_note = f"  ({thing.ven_kind})" if thing.ven_kind == "place" else ""
    return fmt.ok(
        f"Renamed · {old_disp} → {fmt.named_ref(updated.name, ref)}"
        f"{kind_note}  ·  story {story_when}  ·  {event_code}"
    )


def _instances(world: World, arg: str) -> str:
    """List all instances of a prime VEN."""
    if not arg.strip():
        return fmt.hint("Usage: instances <ven-slug-or-name>")
    ven = world.find_ven(arg.strip())
    if not ven:
        return fmt.err(f"No VEN matching {arg.strip()!r}.  Use vens.")
    insts = world.list_instances_of_ven(ven.id)
    kind_lbl = format_kind_label(ven.kind, ven.subtype)
    code_bit = (ven.code or "").strip() or ven.slug
    lines = [
        fmt.title_line(f"Instances · {display_name(ven.name)}"),
        fmt.hint(f"{kind_lbl}  ·  {code_bit}  ·  {len(insts)} instance(s)"),
    ]
    if not insts:
        lines.append(fmt.hint(f"None yet.  spawn {ven.slug} as <title>"))
        return fmt.join_blocks(*lines, gap=0)
    for inst in insts:
        ref = world.short_ref_of(inst.id)
        lines.append(
            fmt.stacked_item(
                fmt.named_ref(inst.name, ref),
                _candidate_detail(world, inst, include_ref=False),
                kind=inst.ven_kind,
            )
        )
    # Targeting: compact code once + where/slug — not legacy book open
    sample_ref = world.short_ref_of(insts[0].id)
    if _is_folio_kind(ven.kind):
        verb = "folio open"
    else:
        verb = "examine"
    lines.append(
        fmt.hint(
            f"Target: #{sample_ref}  ·  {ven.slug} here|inv  ·  e.g. {verb} {ven.slug}"
        )
    )
    return "\n".join(lines)


def _despawn(world: World, arg: str) -> str:
    """
    Soft-despawn: move a reachable takeable instance into Lost Dept.

    despawn <thing>  ·  lose <thing>
    """
    if not arg.strip():
        return fmt.hint(
            "Usage: despawn <thing>  ·  lose <thing>\n"
            "  Sends the instance to Lost Dept (not deleted).  "
            "List: lost  ·  Restore: reclaim <thing>"
        )
    thing, err = _resolve_instance_target(world, arg.strip())
    if err or thing is None:
        # Prefer reachable only for lose
        thing2, err2 = _resolve_one(world, arg.strip())
        if thing2 is None:
            return err or err2 or fmt.err(f"No match for {arg!r}.")
        thing = thing2
    # Must be reachable (here / inv / nested), not a global layer name alone
    if not world.is_reachable(thing.id):
        return fmt.err(
            f"{display_name(thing.name)} is not here or carried.  "
            f"Pick it up or stand where it is."
        )
    prior = world.container_of(thing.id)
    try:
        dept_id, _prior_id = world.lose_instance(thing.id)
    except ValueError as e:
        return fmt.err(str(e))

    def undo_lose(
        w: World,
        iid=thing.id,
        prev=prior,
    ) -> None:
        if prev is None:
            # Drop onto current place floor if no prior container
            loc = w.player_location()
            if loc:
                w.put_in(iid, loc.id, slot="interior")
            return
        w.put_in(iid, prev[0], slot=prev[1])

    world.undo_stack.push(f"despawn {thing.name}", undo_lose)
    dept = world.get_instance(dept_id)
    dname = display_name(dept.name) if dept else "Lost Dept"
    return fmt.join_blocks(
        fmt.ok(f"Lost · {display_name(thing.name)}  →  {dname}"),
        fmt.hint(
            f"Not deleted  ·  lost  ·  reclaim {display_name(thing.name)}  ·  undo"
        ),
        gap=0,
    )


def _reclaim(world: World, arg: str) -> str:
    """Pull something out of Lost Dept into inventory."""
    if not arg.strip():
        return fmt.hint(
            "Usage: reclaim <thing>  ·  unlose <thing>\n"
            "  Pulls from Lost Dept into inventory.  List: lost"
        )
    q = arg.strip()
    thing = world.find_lost_named(q)
    if thing is None:
        # ambiguous or missing
        hits = [
            c
            for c in world.list_lost_contents()
            if True  # collect for message
        ]
        names = [display_name(c.name) for c in hits[:12]]
        return fmt.err(
            f"No lost thing matching {q!r}."
            + (f"  In Lost Dept: {', '.join(names)}" if names else "  lost  to list")
        )
    prior = world.container_of(thing.id)
    try:
        world.reclaim_instance(thing.id)
    except ValueError as e:
        return fmt.err(str(e))

    def undo_reclaim(w: World, iid=thing.id, prev=prior) -> None:
        if prev:
            w.put_in(iid, prev[0], slot=prev[1])
        else:
            w.lose_instance(iid)

    world.undo_stack.push(f"reclaim {thing.name}", undo_reclaim)
    return fmt.join_blocks(
        fmt.ok(f"Reclaimed · {display_name(thing.name)}  →  inventory"),
        fmt.hint("Carried again  ·  despawn to return to Lost Dept"),
        gap=0,
    )


def _lost_list(world: World, arg: str = "") -> str:
    """List soft-despawned instances in Lost Dept."""
    dept = world.ensure_lost_dept()
    items = world.list_lost_contents()
    lines = [
        fmt.title_line(f"Lost Dept · {display_name(dept.name)}", kind="place"),
        fmt.hint("Soft landfill — nothing is destroyed  ·  reclaim <name>"),
    ]
    if not items:
        lines.append(fmt.hint("(empty)  ·  despawn <thing> to shelve an instance here"))
    else:
        for it in items:
            ref = world.short_ref_of(it.id)
            lines.append(
                fmt.bullet(
                    it.name,
                    f"{it.ven_kind}  ·  {display_name(it.ven_name)}  ·  #{ref}",
                    kind=it.ven_kind,
                )
            )
        lines.append(fmt.hint("reclaim <name>  ·  despawn <thing>  ·  undo"))
    return "\n".join(lines)


def _split_put_args(arg: str) -> tuple[str, str] | None:
    """Split ``put <thing> in|into|on|onto <container…>`` (prefer longer sep first)."""
    lower = arg.lower()
    # on/onto: natural for tables, shelves, trays (same placement as in/into)
    for sep in (" into ", " onto ", " in ", " on "):
        if sep in lower:
            idx = lower.find(sep)
            left = arg[:idx].strip()
            right = arg[idx + len(sep) :].strip()
            if left and right:
                return left, right
    return None


def _resolve_put_destination(
    world: World, cont_name: str
) -> tuple[InstanceView | None, str | None]:
    """
    Resolve put destination: reachable container, current place, player, or exit neighbor.

    Nearby rooms (one exit hop) count as present so you can move people/objects
    next door without inventory. Player is excluded from normal here-candidates
    (you *are* them), so me / builder / name match is explicit.
    """
    from .ids import names_match

    key = cont_name.strip()
    if not key:
        return None, fmt.hint(
            "Usage: put <thing> in|on <container|exit|place>"
        )
    low = key.lower()
    if low in ("here", "room", "floor", "ground", "place"):
        loc = world.player_location()
        if not loc:
            return None, fmt.hint("Nowhere.")
        return loc, None
    if low in ("me", "self", "i", "you", "player", "inv", "inventory"):
        player = _player_instance(world)
        if not player:
            return None, fmt.hint("No player set.")
        return player, None

    player = _player_instance(world)
    if player is not None and names_match(key, player.name):
        return player, None

    cont = world.resolve_here_named(key)
    if cont is not None:
        return cont, None

    neighbors = world.resolve_adjacent_place(key)
    if len(neighbors) == 1:
        return neighbors[0], None
    if len(neighbors) > 1:
        return None, _format_ambiguous(world, key, neighbors)

    return None, fmt.err(
        f"No container or nearby place {key!r}.\n"
        + fmt.hint(
            "put <thing> in|on <box|person|me>  ·  put <thing> in <path>  ·  "
            "put <thing> in <adjacent place>  ·  paths"
        )
    )


def _put(world: World, arg: str) -> str:
    from .story_when import peel_when_anywhere

    if not arg:
        return fmt.hint(
            "Usage: put <thing> in|into|on|onto <container|path|nearby place> [slot] "
            "[when @N | --when 0]\n"
            "  put hope in cartographer  ·  put silver on tray  ·  put silver in box --when 1\n"
            "  Inner life: put <sense|…> in <person>  (slot auto = kind)"
        )
    arg, story_when, node_index = peel_when_anywhere(arg)
    split = _split_put_args(arg)
    if not split:
        return fmt.hint(
            "Usage: put <thing> in|into|on|onto <container|path|nearby place> [slot] "
            "[when @N | --when 0]\n"
            "  put silver in box  ·  put silver on table  ·  put Archivist into Side Alcove\n"
            "  Inner life: put <goal|feeling|…> in <person>  (slot auto = kind)"
        )
    thing_name, rest_s = split
    rest = rest_s.split()
    if not rest:
        return fmt.hint(
            "Usage: put <thing> in|on <container|exit|nearby place> [slot]"
        )
    slot = "interior"
    slot_explicit = False
    if rest[-1] in CONTAINMENT_SLOTS:
        slot = rest[-1]
        slot_explicit = True
        cont_name = " ".join(rest[:-1])
    else:
        cont_name = " ".join(rest)
    if not cont_name:
        return fmt.hint(
            "Usage: put <thing> in|on <container|exit|nearby place> [slot]"
        )

    thing = world.resolve_here_named(thing_name)
    if not thing:
        return fmt.err(f"No {thing_name!r} here.")
    cont, cerr = _resolve_put_destination(world, cont_name)
    if cerr or cont is None:
        return cerr or fmt.err(f"No container or nearby place {cont_name!r}.")
    if thing.id == cont.id:
        return fmt.err("Cannot put something into itself.")

    player = _player_instance(world)
    # Into the builder → inventory (not inner life), unless slot explicit
    if (
        not slot_explicit
        and player is not None
        and cont.id == player.id
    ):
        slot = "inventory"
    # Person + sense / person-archetype → Inner life slot unless user set one
    elif (
        not slot_explicit
        and cont.ven_kind == "person"
        and is_inner_life_kind(thing.ven_kind, thing.ven_subtype)
    ):
        slot = default_inner_slot(thing.ven_kind, thing.ven_subtype)
    # Places always use interior (floor of that room)
    if cont.ven_kind == "place" and not slot_explicit:
        slot = "interior"
    # Containers (house, box) default interior when entered as put target
    from .world import BIN_KINDS

    if cont.ven_kind in BIN_KINDS and not slot_explicit:
        slot = "interior"

    prior = world.container_of(thing.id)
    world.put_in(thing.id, cont.id, slot=slot)
    _push_put_undo(world, thing.id, prior, f"put {thing.name}")
    tname = display_name(thing.name)
    cname = display_name(cont.name)
    extra: list[tuple[InstanceView, str, str]] = []
    # If it left the builder's inventory, also log give on the player
    if (
        player
        and prior
        and prior[0] == player.id
        and cont.id != player.id
    ):
        extra.append((player, "give", f"put {tname} into {cname}"))
    code = _record_move_history(
        world,
        thing,
        verb="put",
        story_when=story_when,
        node_index=node_index,
        note=f"into {cname} [{slot}]",
        also=cont,
        also_verb="receive",
        also_note=f"received {tname} [{slot}]",
        extra_legs=extra or None,
    )
    if cont.ven_kind == "place":
        main = (
            f"Moved · {thing.name} → {cont.name}  ·  "
            f"story {story_when}  ·  {code}"
        )
    else:
        main = (
            f"Put · {thing.name} in {cont.name} [{slot}]  ·  "
            f"story {story_when}  ·  {code}"
        )
    # Installed into a device with a living portal → ready to run (no re-bind)
    moved = world.get_instance(thing.id) or thing
    portal_id = world.get_portal_to(moved.id)
    if (
        portal_id
        and cont.ven_kind != "place"
        and (player is None or cont.id != player.id)
        and world.install_container_of(moved.id) is not None
    ):
        dest = world.get_instance(portal_id)
        dname = display_name(dest.name) if dest else "bound place"
        return fmt.join_blocks(
            fmt.ok(main),
            fmt.hint(
                f"portal → {dname}  ·  run {display_name(moved.name)} "
                f"(binding kept)"
            ),
            gap=0,
        )
    return fmt.ok(main)


def _elevate(world: World, arg: str) -> str:
    if not arg:
        return fmt.hint(
            "Usage: elevate <thing> [as <new prime name>]  ·  "
            "elevate <thing> -> <new prime name>"
        )
    prime_name = None
    target = arg.strip()
    split = split_as_title(arg)
    if split:
        target, prime_name = split
        if not prime_name:
            return fmt.hint("Usage: elevate <thing> [as|-> <new prime name>]")
    thing = world.resolve_here_named(target)
    if not thing:
        # allow unique global name
        found = world.find_instances_by_name(target)
        if len(found) == 1:
            thing = found[0]
        elif len(found) > 1:
            return _format_ambiguous(world, target, found)
        else:
            return fmt.err(f"No {target!r} here.")
    origin_ven_id = thing.ven_id
    origin_slug = thing.ven_slug
    st = world.instance_state(thing.id)
    old_short_ref = st.get("short_ref")
    inst_id = thing.id
    ven_id = world.elevate_instance_to_prime(thing.id, name=prime_name)

    def undo_elevate(
        w: World,
        iid=inst_id,
        vid=ven_id,
        ovid=origin_ven_id,
        oref=old_short_ref,
    ) -> None:
        w.conn.execute(
            """
            UPDATE instances
            SET became_prime_ven_id = NULL, ven_id = ?
            WHERE id = ?
            """,
            (ovid, iid),
        )
        w.conn.commit()
        st2 = w.instance_state(iid)
        if oref is not None:
            st2["short_ref"] = oref
        else:
            st2.pop("short_ref", None)
        w.set_instance_state(iid, st2)
        w.delete_ven(vid)

    world.undo_stack.push(f"elevate {thing.name}", undo_elevate)
    ven = world.get_ven(ven_id)
    assert ven is not None
    ref = world.short_ref_of(inst_id)
    return fmt.join_blocks(
        fmt.ok(f"Elevated · new Prime VEN {ven.name} ({ven.slug})"),
        fmt.hint(
            f"parent {origin_slug}  ·  lived copy rebound as #{ref}  ·  of this prime"
        ),
        gap=0,
    )


def _vens_types(world: World) -> str:
    """
    Kind / subtype census for this world (no prime names).

    Each row is a flavor in use: person, place/room, thing/key, …
    """
    # (kind, subtype|None) → (prime_count, instance_count)
    tallies: dict[tuple[str, str | None], list[int]] = {}
    for v in world.list_vens():
        if v is None:
            continue
        k = (v.kind or "other").strip().lower() or "other"
        sub = (v.subtype or "").strip().lower() or None
        key = (k, sub)
        if key not in tallies:
            tallies[key] = [0, 0]
        tallies[key][0] += 1
        tallies[key][1] += len(world.list_instances_of_ven(v.id))

    if not tallies:
        return fmt.join_blocks(
            fmt.section("VEN types"),
            fmt.hint("No primes yet.  create <kind[/subtype]> <name>"),
            fmt.hint("Engine roots: " + ", ".join(KINDS)),
            gap=0,
        )

    # Sort: KINDS order, then bare kind, then subtypes A–Z
    kind_order = {k: i for i, k in enumerate(KINDS)}

    def sort_key(item: tuple[tuple[str, str | None], list[int]]) -> tuple:
        (k, sub), _ = item
        return (kind_order.get(k, 999), k, sub is not None, sub or "")

    rows_sorted = sorted(tallies.items(), key=sort_key)

    # Display rows: kind, sub label, primes, insts, create hint
    display: list[tuple[str, str, str, str, str]] = []
    for (k, sub), (np, ni) in rows_sorted:
        sub_s = sub if sub else "—"
        flavor = f"{k}/{sub}" if sub else k
        display.append((k, sub_s, str(np), str(ni), flavor))

    w_kind = max(4, max(len(r[0]) for r in display), len("KIND"))
    w_sub = max(3, max(len(r[1]) for r in display), len("SUB"))
    w_p = max(5, max(len(r[2]) for r in display), len("PRIMES"))
    w_i = max(4, max(len(r[3]) for r in display), len("INST"))
    gap = "  "

    header = (
        f"  [dim]{fmt.safe(fmt.pad_visible('KIND', w_kind))}{gap}"
        f"{fmt.safe(fmt.pad_visible('SUB', w_sub))}{gap}"
        f"{fmt.safe(fmt.pad_visible('PRIMES', w_p))}{gap}"
        f"INST[/dim]"
    )
    rule = (
        f"  [dim]{'-' * w_kind}{gap}"
        f"{'-' * w_sub}{gap}"
        f"{'-' * w_p}{gap}"
        f"{'-' * w_i}[/dim]"
    )
    lines = [
        fmt.section("VEN types · in this world"),
        header,
        rule,
    ]
    for k, sub_s, np, ni, flavor in display:
        lines.append(
            f"  {fmt.colored_padded_name(k, k, w_kind)}{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(sub_s, w_sub))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(np, w_p))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(ni, w_i))}[/dim]"
        )

    # Unused engine roots (optional scan aid)
    used_kinds = {k for (k, _) in tallies}
    unused = [k for k in KINDS if k not in used_kinds]
    lines.append("")
    if unused:
        lines.append(
            fmt.hint("Unused roots: " + ", ".join(unused))
        )
    lines.append(
        fmt.hint(
            "create <kind/sub> <name>  ·  vens <kind>  ·  vens  ·  help kinds"
        )
    )
    return "\n".join(lines)


def _list_vens(world: World, arg: str) -> str:
    """
    Prime VEN catalog — mini-table with kind + subtype:

      CODE     NAME     KIND    SUB        INST  OF  SLUG
      -------  -------  ------  ---------  ----  --  -------
      PER-001  Builder  person  archetype  1     —   BUILDER
    """
    arg = arg.strip()
    low = arg.lower()
    if low in ("types", "type", "subtypes", "subtype"):
        return _vens_types(world)
    if low == "tree" or low.startswith("tree "):
        root_q = arg[4:].strip() if low.startswith("tree") else ""
        return _vens_tree(world, root_q)
    if low.startswith("rename ") or low.startswith("call "):
        rest = arg.split(maxsplit=1)[1].strip() if " " in arg else ""
        return _vens_rename(world, rest)
    if low.startswith("export "):
        return _vens_export(world, arg[7:].strip())
    if low in ("load", "import", "collector") or low.startswith(
        ("load ", "import ")
    ):
        rest = ""
        if low.startswith("load "):
            rest = arg[5:].strip()
        elif low.startswith("import "):
            rest = arg[7:].strip()
        return _vens_load(world, rest)
    if low == "export":
        return fmt.hint(
            "Usage: vens export <prime name|code|slug>\n"
            "  Writes ~/.aidm/ven-collector/{seq}-{CODE}-{slug}.ven"
        )

    kind = arg.lower() or None
    if kind and kind not in KINDS:
        return fmt.err(
            f"Unknown kind {kind!r}.  Or: vens types  ·  vens tree  ·  "
            f"vens export  ·  vens load"
        )
    vens = world.list_vens(kind)
    if not vens:
        return fmt.hint("No VENs." + (f"  (kind {kind})" if kind else ""))

    # Plain columns: code, name, kind, subtype, inst count, parent, slug
    rows: list[tuple[str, str, str, str, str, str, str, str]] = []
    for v in vens:
        n = len(world.list_instances_of_ven(v.id))
        parent = world.parent_of(v.id)
        if parent is not None:
            of_bit = (parent.code or parent.slug or display_name(parent.name)).strip()
        else:
            of_bit = "—"
        code = (v.code or "—").strip() or "—"
        sub = (v.subtype or "").strip() or "—"
        rows.append(
            (
                code,
                display_name(v.name),
                v.kind,
                sub,
                str(n),
                of_bit,
                v.slug or "—",
                v.kind,  # for coloring
            )
        )

    w_code = max(4, max(len(r[0]) for r in rows), len("CODE"))
    w_name = max(4, max(len(r[1]) for r in rows), len("NAME"))
    w_kind = max(4, max(len(r[2]) for r in rows), len("KIND"))
    w_sub = max(3, max(len(r[3]) for r in rows), len("SUB"))
    w_inst = max(4, max(len(r[4]) for r in rows), len("INST"))
    w_of = max(2, max(len(r[5]) for r in rows), len("OF"))
    w_slug = max(4, max(len(r[6]) for r in rows), len("SLUG"))
    gap = "  "

    header = (
        f"  [dim]{fmt.safe(fmt.pad_visible('CODE', w_code))}{gap}"
        f"{fmt.safe(fmt.pad_visible('NAME', w_name))}{gap}"
        f"{fmt.safe(fmt.pad_visible('KIND', w_kind))}{gap}"
        f"{fmt.safe(fmt.pad_visible('SUB', w_sub))}{gap}"
        f"{fmt.safe(fmt.pad_visible('INST', w_inst))}{gap}"
        f"{fmt.safe(fmt.pad_visible('OF', w_of))}{gap}"
        f"SLUG[/dim]"
    )
    rule = (
        f"  [dim]{'-' * w_code}{gap}"
        f"{'-' * w_name}{gap}"
        f"{'-' * w_kind}{gap}"
        f"{'-' * w_sub}{gap}"
        f"{'-' * w_inst}{gap}"
        f"{'-' * w_of}{gap}"
        f"{'-' * w_slug}[/dim]"
    )

    title = "Prime VENs" + (f" · {kind}" if kind else "")
    lines = [
        fmt.section(title),
        header,
        rule,
    ]
    for code, name, vkind, sub, n_s, of_bit, slug, color_kind in rows:
        lines.append(
            f"  [dim]{fmt.safe(fmt.pad_visible(code, w_code))}[/dim]{gap}"
            f"{fmt.colored_padded_name(name, color_kind, w_name)}{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(vkind, w_kind))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(sub, w_sub))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(n_s, w_inst))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(of_bit, w_of))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(slug, w_slug))}[/dim]"
        )
    lines.append("")
    lines.append(
        fmt.hint(
            "instances <code|slug>  ·  spawn <code|slug> as <title>  ·  "
            "vens types  ·  vens tree  ·  vens export  ·  vens load  ·  vens <kind>"
        )
    )
    return "\n".join(lines)


def _ven_cmd(world: World, arg: str) -> str:
    """ven load [pack]  ·  ven export <prime>  ·  ven rename … (aliases under vens)."""
    arg = arg.strip()
    low = arg.lower()
    if not arg or low in ("load", "import", "collector"):
        return _vens_load(world, "")
    if low.startswith("load ") or low.startswith("import "):
        rest = arg.split(maxsplit=1)[1].strip()
        return _vens_load(world, rest)
    if low.startswith("export "):
        return _vens_export(world, arg[7:].strip())
    if low == "export":
        return fmt.hint("Usage: ven export <prime>  ·  ven load [pack]")
    if low.startswith("rename ") or low.startswith("call "):
        rest = arg.split(maxsplit=1)[1].strip() if " " in arg else ""
        return _vens_rename(world, rest)
    return fmt.hint(
        "Usage: ven load [pack]  ·  ven export <prime>  ·  "
        "ven rename <prime> as <name>\n"
        "  Collector: ~/.aidm/ven-collector/"
    )


def _vens_rename(world: World, arg: str) -> str:
    """
    Rename a prime's formal name (e.g. Builder → your name).

    vens rename Builder as Ada
    vens rename Builder -> Ada
    vens rename PER-001 as Ada reslug   # optional: refresh cute slug
    """
    raw = (arg or "").strip()
    split = split_as_title(raw)
    if not split:
        return fmt.hint(
            "Usage: vens rename <prime> as <new name> [reslug]\n"
            "  also: vens rename <prime> -> <new name> [reslug]\n"
            "  e.g. vens rename Builder -> Ada\n"
            "  renames the prime formal name; code stays put.  "
            "Optional reslug refreshes the cute slug."
        )
    left, right = split
    reslug = False
    # trailing reslug / re-slug
    bits = right.rsplit(None, 1)
    if len(bits) == 2 and bits[1].lower() in ("reslug", "re-slug", "slug"):
        new_name, reslug = bits[0].strip(), True
    else:
        new_name = right
    if not left or not new_name:
        return fmt.hint(
            "Usage: vens rename <prime> as|-> <new name> [reslug]"
        )
    ven = world.find_ven(left)
    if ven is None:
        return fmt.err(f"No prime matching {left!r}.  Try: vens")
    prior = ven.name
    prior_slug = ven.slug
    try:
        updated = world.set_ven_name(ven.id, new_name, reslug=reslug)
    except Exception as e:  # noqa: BLE001
        return fmt.err(str(e))

    def undo_rename(
        w: World,
        vid: str = ven.id,
        old_name: str = prior,
        old_slug: str = prior_slug,
        did_reslug: bool = reslug,
    ) -> None:
        if did_reslug:
            w.conn.execute(
                "UPDATE vens SET name = ?, slug = ? WHERE id = ?",
                (old_name, old_slug, vid),
            )
            w.conn.commit()
        else:
            w.set_ven_name(vid, old_name, reslug=False)

    world.undo_stack.push(f"vens rename {prior}", undo_rename)
    slug_note = (
        f"  ·  slug {prior_slug} → {updated.slug}"
        if reslug and prior_slug != updated.slug
        else f"  ·  slug {updated.slug}"
    )
    return fmt.join_blocks(
        fmt.ok(
            f"Prime renamed · {display_name(prior)} → {display_name(updated.name)}"
        ),
        fmt.hint(f"{updated.code or '—'}{slug_note}  ·  code unchanged"),
        gap=0,
    )


def _vens_export(world: World, query: str) -> str:
    """
    Export to ~/.aidm/ven-collector/.

    Prefer a reachable **instance** when the match is unique here (books, files,
    retitled copies). Otherwise export the **prime**. Force with:
      vens export prime <match>  ·  vens export inst <match>
    """
    from .ven_pack import (
        export_instance,
        export_ven,
        ven_collector_dir,
        world_label,
    )

    q = (query or "").strip()
    if not q:
        return fmt.hint(
            "Usage: vens export <name|code>\n"
            "       vens export inst <thing>   ·  vens export prime <ven>\n"
            "  Instance packs include the prime + this copy's title/desc/lore/pages.\n"
            "  Primes alone: desc, lore, wiki soft-links, template book pages."
        )

    force_inst = False
    force_prime = False
    low = q.lower()
    if low.startswith("inst ") or low.startswith("instance "):
        force_inst = True
        q = q.split(maxsplit=1)[1].strip()
    elif low.startswith("prime ") or low.startswith("ven "):
        force_prime = True
        q = q.split(maxsplit=1)[1].strip()

    origin = world_label(world)
    inst: InstanceView | None = None
    ven = None

    if not force_prime:
        # Reachable instance first (here / inv / nested)
        found, _err = _resolve_one(world, q)
        if found is not None:
            inst = found
        elif not force_inst:
            # Unique global instance by name
            hits = world.find_instances_by_name(q)
            if len(hits) == 1:
                inst = hits[0]
            elif len(hits) > 1 and force_inst:
                return _format_ambiguous(world, q, hits)

    if force_inst and inst is None:
        hits = world.find_instances_by_name(q)
        if len(hits) == 1:
            inst = hits[0]
        elif len(hits) > 1:
            return _format_ambiguous(world, q, hits)
        else:
            return fmt.err(
                f"No instance matching {q!r}.  Try: here/inv  ·  examine"
            )

    if inst is not None and not force_prime:
        try:
            path = export_instance(world, inst, origin_world=origin)
        except Exception as e:  # noqa: BLE001
            return fmt.err(str(e))
        ref = world.short_ref_of(inst.id)
        return fmt.join_blocks(
            fmt.ok(
                f"Exported instance · {fmt.named_ref(inst.name, ref)}"
            ),
            fmt.hint(
                f"prime {inst.ven_code or inst.ven_slug}  ·  pack includes prime definition"
            ),
            fmt.hint(f"→ {path}"),
            fmt.hint(f"Collector  ·  {ven_collector_dir()}"),
            gap=0,
        )

    ven = world.find_ven(q)
    if ven is None:
        return fmt.err(
            f"No prime or unique instance matching {q!r}.  "
            f"Try: vens  ·  vens export inst <thing>"
        )
    try:
        path = export_ven(world, ven, origin_world=origin)
    except Exception as e:  # noqa: BLE001
        return fmt.err(str(e))
    code = ven.code or "—"
    return fmt.join_blocks(
        fmt.ok(f"Exported prime · {display_name(ven.name)}  ({code})"),
        fmt.hint(f"→ {path}"),
        fmt.hint(f"Collector  ·  {ven_collector_dir()}"),
        fmt.hint("Load in any world:  vens load  ·  ven load <file>"),
        gap=0,
    )


def _vens_load(world: World, query: str) -> str:
    """List collector packs or import one into this world."""
    from .ven_pack import (
        find_pack,
        import_pack,
        list_packs,
        load_pack_file,
        ven_collector_dir,
        world_label,
    )

    q = (query or "").strip()
    root = ven_collector_dir()
    if not q:
        packs = list_packs(root)
        if not packs:
            return fmt.hint(
                f"No .ven packs in {root}\n"
                f"  Export:  vens export <prime|instance>"
            )
        # Mini table
        rows = [
            (
                f"{p.seq:04d}",
                p.code or "—",
                display_name(p.name),
                p.kind or "—",
                "inst" if p.pack_kind == "instance" else "prime",
                p.origin_world or "—",
                p.path.name,
            )
            for p in packs
        ]
        w_seq = max(3, max(len(r[0]) for r in rows), len("SEQ"))
        w_code = max(4, max(len(r[1]) for r in rows), len("CODE"))
        w_name = max(4, max(len(r[2]) for r in rows), len("NAME"))
        w_kind = max(4, max(len(r[3]) for r in rows), len("KIND"))
        w_mode = max(4, max(len(r[4]) for r in rows), len("MODE"))
        w_orig = max(4, max(len(r[5]) for r in rows), len("ORIGIN"))
        gap = "  "
        header = (
            f"  [dim]{fmt.safe(fmt.pad_visible('SEQ', w_seq))}{gap}"
            f"{fmt.safe(fmt.pad_visible('CODE', w_code))}{gap}"
            f"{fmt.safe(fmt.pad_visible('NAME', w_name))}{gap}"
            f"{fmt.safe(fmt.pad_visible('KIND', w_kind))}{gap}"
            f"{fmt.safe(fmt.pad_visible('MODE', w_mode))}{gap}"
            f"{fmt.safe(fmt.pad_visible('ORIGIN', w_orig))}{gap}"
            f"FILE[/dim]"
        )
        rule = (
            f"  [dim]{'-' * w_seq}{gap}{'-' * w_code}{gap}{'-' * w_name}{gap}"
            f"{'-' * w_kind}{gap}{'-' * w_mode}{gap}{'-' * w_orig}{gap}----[/dim]"
        )
        lines = [
            fmt.section("VEN collector"),
            fmt.hint(str(root)),
            header,
            rule,
        ]
        for seq, code, name, kind, mode, orig, fname in rows:
            lines.append(
                f"  [dim]{fmt.safe(fmt.pad_visible(seq, w_seq))}[/dim]{gap}"
                f"[dim]{fmt.safe(fmt.pad_visible(code, w_code))}[/dim]{gap}"
                f"{fmt.colored_padded_name(name, kind if kind != '—' else None, w_name)}{gap}"
                f"[dim]{fmt.safe(fmt.pad_visible(kind, w_kind))}[/dim]{gap}"
                f"[dim]{fmt.safe(fmt.pad_visible(mode, w_mode))}[/dim]{gap}"
                f"[dim]{fmt.safe(fmt.pad_visible(orig, w_orig))}[/dim]{gap}"
                f"[dim]{fmt.safe(fname)}[/dim]"
            )
        lines.append("")
        lines.append(
            fmt.hint(
                "ven load <seq|code|file>  ·  vens export <prime|instance>"
            )
        )
        return "\n".join(lines)

    path = find_pack(q, root)
    if path is None:
        return fmt.err(
            f"No pack matching {q!r}.  Try: ven load  (lists collector)"
        )
    loc = world.player_location()
    try:
        pack = load_pack_file(path)
        ven_id, local_code, inst_id, remap = import_pack(
            world,
            pack,
            target_world_label=world_label(world),
            place_instance_id=loc.id if loc else None,
        )
    except Exception as e:  # noqa: BLE001
        return fmt.err(str(e))
    ven = world.get_ven(ven_id)
    assert ven is not None
    pack_kind = str(
        pack.get("pack_kind")
        or (pack.get("provenance") or {}).get("pack_kind")
        or "prime"
    )
    already = remap and "already imported" in remap.lower()
    if pack_kind == "instance" and inst_id:
        inst = world.get_instance(inst_id)
        title = display_name(inst.name) if inst else display_name(ven.name)
        ref = world.short_ref_of(inst_id)
        if already:
            bits = [
                fmt.ok(f"Already here · {fmt.named_ref(title, ref)}"),
                fmt.hint("same origin instance — no duplicate created"),
            ]
        else:
            bits = [
                fmt.ok(f"Imported instance · {fmt.named_ref(title, ref)}"),
                fmt.hint(
                    f"prime {local_code}  ·  {ven.kind}  ·  from {path.name}"
                ),
            ]
    else:
        bits = [
            fmt.ok(f"Imported prime · {display_name(ven.name)}  ({local_code})"),
            fmt.hint(f"from {path.name}  ·  kind {ven.kind}  ·  slug {ven.slug}"),
        ]
    if remap and not already:
        bits.append(fmt.hint(remap))
    elif remap and already and "remapped" in remap.lower():
        bits.append(fmt.hint(remap.split("·")[0].strip()))
    prov = pack.get("provenance") or {}
    if prov.get("origin_world"):
        bits.append(fmt.hint(f"came from {prov['origin_world']}"))
    if pack_kind == "instance" and inst_id:
        bits.append(
            fmt.hint(
                f"here if you stood in a place  ·  instances {local_code}"
            )
        )
    else:
        bits.append(
            fmt.hint(
                f"spawn {local_code}  ·  instances {local_code}  ·  vens {ven.kind}"
            )
        )
    return fmt.join_blocks(*bits, gap=0)


def _vens_tree(world: World, root_query: str) -> str:
    """Indented specialization tree."""
    if root_query:
        root = world.find_ven(root_query)
        if root is None:
            return fmt.err(f"No VEN matching {root_query!r}.")
        roots = [root]
        title = f"VEN tree · {display_name(root.name)}"
    else:
        # All roots that have children, plus orphans with no parent
        all_roots = world.root_vens()
        # Show every root (may be long); compact kind filter not needed v1
        roots = all_roots
        title = "VEN tree · roots"

    lines = [fmt.section(title)]
    if not roots:
        return fmt.hint("No root VENs.")

    def walk(ven, depth: int, seen: set[str]) -> None:
        if ven.id in seen:
            lines.append("  " * depth + fmt.hint(f"… cycle at {ven.slug}"))
            return
        seen = seen | {ven.id}
        n = len(world.list_instances_of_ven(ven.id))
        indent = "  " * depth
        mark = "└─ " if depth else ""
        lines.append(
            f"{indent}{mark}{fmt.colored_name(display_name(ven.name), ven.kind)}  "
            f"[dim]{ven.kind}  ·  {ven.slug}  ·  {n} inst[/dim]"
        )
        for ch in world.children_of(ven.id):
            walk(ch, depth + 1, seen)

    for r in roots:
        # Skip pure leaves when showing all roots? Include all for clarity.
        walk(r, 0, set())
    lines.append(fmt.hint("create … of <parent>  ·  elevate <thing> as <name>  ·  lineage <ven>"))
    return "\n".join(lines)


def _lineage(world: World, arg: str) -> str:
    if not arg.strip():
        return fmt.hint("Usage: lineage <ven|instance name>")
    q = arg.strip()
    ven = world.find_ven(q)
    inst = None
    if ven is None:
        thing, err = _resolve_one(world, q)
        if thing is not None:
            inst = thing
            ven = world.get_ven(thing.ven_id)
        else:
            found = world.find_instances_by_name(q)
            if len(found) == 1:
                inst = found[0]
                ven = world.get_ven(inst.ven_id)
            elif len(found) > 1:
                return _format_ambiguous(world, q, found)
            else:
                return err if err else fmt.err(f"No VEN or instance matching {q!r}.")
    if ven is None:
        return fmt.err(f"No VEN matching {q!r}.")
    path = world.lineage_path(ven.id)
    labels = [display_name(v.name) for v in path]
    if inst is not None:
        labels.append(f"{display_name(inst.name)} (#{world.short_ref_of(inst.id)})")
    return fmt.join_blocks(
        fmt.section("Lineage"),
        fmt.hint(" › ".join(labels)),
        gap=0,
    )


def _compose(world: World, arg: str) -> str:
    """
    compose <whole> [deep]          — list parts (deep = nested composition)
    compose <whole> + <part> [as role]
    compose <whole> - <part> [role]
    """
    from .wiki import composition_depth_for_deep, format_composition_tree_lines, parse_deep_flag

    arg = arg.strip()
    if not arg:
        return fmt.hint(
            "Usage: compose <whole> [deep]  ·  compose <whole> + <part> [as role]\n"
            "       compose <whole> - <part> [role]"
        )
    # add: whole + part [as role]
    if " + " in arg:
        left, right = arg.split(" + ", 1)
        whole_q = left.strip()
        right = right.strip()
        role = "part"
        part_q = right
        if " as " in right.lower():
            idx = right.lower().rfind(" as ")
            part_q, role = right[:idx].strip(), right[idx + 4 :].strip() or "part"
        whole = world.find_ven(whole_q)
        part = world.find_ven(part_q)
        if whole is None:
            return fmt.err(f"No whole VEN matching {whole_q!r}.")
        if part is None:
            return fmt.err(f"No part VEN matching {part_q!r}.")
        try:
            pid = world.add_ven_part(whole.id, part.id, role=role)
        except Exception as e:  # noqa: BLE001
            return fmt.err(str(e))

        def undo_add(w: World, wid=whole.id, paid=part.id, r=role.lower()) -> None:
            w.remove_ven_part(wid, paid, role=r)

        world.undo_stack.push(f"compose + {part.name}", undo_add)
        return fmt.ok(
            f"Composed · {display_name(whole.name)} + "
            f"{display_name(part.name)} [{role}]"
        )

    # remove: whole - part [role]
    if " - " in arg:
        left, right = arg.split(" - ", 1)
        whole_q = left.strip()
        bits = right.strip().split()
        if not bits:
            return fmt.hint("Usage: compose <whole> - <part> [role]")
        # part may be multi-word if no role; if last token looks like role and rest is part
        part_q = right.strip()
        role = None
        # optional trailing role token only if 2+ words and last is simple role-ish
        toks = right.strip().rsplit(None, 1)
        if len(toks) == 2 and toks[1].isalpha() and toks[1].islower():
            # could be "Archetype of Him archetype" 
            part_try, role_try = toks[0], toks[1]
            if world.find_ven(part_try) is not None:
                part_q, role = part_try, role_try
        whole = world.find_ven(whole_q)
        part = world.find_ven(part_q)
        if whole is None:
            return fmt.err(f"No whole VEN matching {whole_q!r}.")
        if part is None:
            return fmt.err(f"No part VEN matching {part_q!r}.")
        n = world.remove_ven_part(whole.id, part.id, role=role)
        if n == 0:
            return fmt.hint("No such composition edge.")
        return fmt.ok(
            f"Removed · {display_name(part.name)} from {display_name(whole.name)}"
            + (f" [{role}]" if role else "")
        )

    # list (optional trailing deep)
    list_q, deep = parse_deep_flag(arg)
    if not list_q:
        return fmt.hint("Usage: compose <whole> [deep]")
    whole = world.find_ven(list_q)
    if whole is None:
        return fmt.err(f"No VEN matching {list_q!r}.")
    tree = world.composition_tree(
        whole.id, max_depth=composition_depth_for_deep(deep)
    )
    title = f"Composed of · {display_name(whole.name)}"
    if deep:
        title += " (deep)"
    lines = [fmt.section(title)]
    if not tree:
        lines.append(
            fmt.hint(
                f"None.  compose {whole.slug} + <part> [as concept|archetype|…]"
            )
        )
    else:
        lines.extend(format_composition_tree_lines(tree))
        if not deep and any(
            world.list_ven_parts(n.part.part_ven_id) for n in tree
        ):
            lines.append(
                fmt.hint(f"Nested parts: compose {whole.slug} deep")
            )
    return "\n".join(lines)


def _timeline(world: World, arg: str) -> str:
    return _layer_cmd(world, "timeline", arg)


def _realm(world: World, arg: str) -> str:
    return _layer_cmd(world, "realm", arg)


def _layer_cmd(world: World, kind: str, arg: str) -> str:
    """timeline / realm management and assignment."""
    arg = arg.strip()
    sub, _, rest = arg.partition(" ")
    sub = sub.lower()
    rest = rest.strip()

    if not arg or sub in ("list", "ls"):
        return _layer_list(world, kind)

    if sub == "create":
        if not rest:
            return fmt.hint(f"Usage: {kind} create <name> [| description]")
        if "|" in rest:
            name, desc = rest.split("|", 1)
            name, desc = name.strip(), desc.strip()
        else:
            name, desc = rest, ""
        ven_id, inst_id = world.create_layer(kind, name, description=desc)

        def undo_layer(w: World, iid=inst_id, vid=ven_id) -> None:
            w.delete_instance(iid)
            w.delete_ven(vid)

        world.undo_stack.push(f"{kind} create", undo_layer)
        ven = world.get_ven(ven_id)
        assert ven is not None
        return fmt.join_blocks(
            fmt.ok(f"{kind} · {ven.name}"),
            fmt.hint(f"ven {ven.slug}  ·  layer instance {inst_id}"),
            fmt.hint(f"Assign with:  {kind} set {ven.name}"),
            gap=0,
        )

    if sub == "here":
        return _locate(world, "self")

    if sub == "clear":
        # clear on current place, or clear on <thing>
        target_name = rest
        return _layer_assign(world, kind, clear=True, target_name=target_name or None)

    if sub == "set":
        # set <layer-name> [on <thing>]
        if not rest:
            return fmt.hint(
                f"Usage: {kind} set <name>  |  {kind} set <name> on <thing here>"
            )
        if " on " in rest.lower():
            idx = rest.lower().rfind(" on ")
            layer_name, target_name = rest[:idx].strip(), rest[idx + 4 :].strip()
        else:
            layer_name, target_name = rest, None
        return _layer_assign(
            world, kind, layer_name=layer_name, target_name=target_name, clear=False
        )

    if sub == "show" or sub == "places":
        # timeline show PRIME / timeline places PRIME
        name = rest if rest else sub  # if someone typed "timeline PRIME"
        if sub in ("show", "places"):
            name = rest
        if not name:
            return fmt.hint(f"Usage: {kind} places <name>")
        return _layer_places(world, kind, name)

    # Bare: timeline PRIME  → show places on that timeline
    # or treat as set if single token looks like a name? Prefer show catalog tip.
    # If arg is a known layer name, show places on it.
    layer = world.resolve_layer(kind, arg)
    if layer:
        return _layer_places(world, kind, arg)

    return fmt.hint(
        f"Usage: {kind} list | create <name> | set <name> [on <thing>] | "
        f"clear [on <thing>] | places <name> | here\n"
        f"  Review current place's {kind}:  lore on {kind}  ·  examine {kind}  ·  "
        f"@desc on {kind}"
    )


def _layer_list(world: World, kind: str) -> str:
    """
    Realm/timeline catalog as an aligned mini-table:

      CODE     NAME           INSTANCE              LOCATIONS
      RLM-001  Terminal       (inst_…)              2 location(s)
    """
    catalog = world.list_layer_catalog(kind)
    if not catalog:
        return fmt.hint(f"No {kind}s yet.  {kind} create <name>")

    # Build plain column values first (widths from visible text)
    rows: list[tuple[str, str, str, str]] = []
    for row in catalog:
        ven = row["ven"]
        inst = row["instance"]
        n = int(row["place_count"] or 0)
        name = display_name(ven.name)
        code = (getattr(ven, "code", None) or "").strip()
        if not code and inst is not None:
            code = world.short_ref_of(inst.id)
        if not code:
            code = "—"
        iid = f"({inst.id})" if inst is not None else "(—)"
        places = f"{n} location(s)"
        rows.append((code, name, iid, places))

    w_code = max(4, max(len(r[0]) for r in rows), len("CODE"))
    w_name = max(4, max(len(r[1]) for r in rows), len("NAME"))
    w_id = max(8, max(len(r[2]) for r in rows), len("INSTANCE"))
    # locations column can stay natural width (right side)

    gap = "  "
    header = (
        f"  [dim]{fmt.safe(fmt.pad_visible('CODE', w_code))}{gap}"
        f"{fmt.safe(fmt.pad_visible('NAME', w_name))}{gap}"
        f"{fmt.safe(fmt.pad_visible('INSTANCE', w_id))}{gap}"
        f"LOCATIONS[/dim]"
    )
    # Column rule under header (matches padded widths + gaps)
    rule = (
        f"  [dim]{'-' * w_code}{gap}"
        f"{'-' * w_name}{gap}"
        f"{'-' * w_id}{gap}"
        f"{'-' * len('LOCATIONS')}[/dim]"
    )
    lines = [
        fmt.section("Timelines" if kind == "timeline" else "Realms"),
        header,
        rule,
    ]
    for code, name, iid, places in rows:
        lines.append(
            f"  [dim]{fmt.safe(fmt.pad_visible(code, w_code))}[/dim]{gap}"
            f"{fmt.colored_padded_name(name, kind, w_name)}{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(iid, w_id))}[/dim]{gap}"
            f"[dim]{fmt.safe(places)}[/dim]"
        )
    # Blank line before helper
    lines.append("")
    lines.append(
        fmt.hint(f"{kind} set <name>  ·  {kind} create <name>  ·  {kind} places <name>")
    )
    return "\n".join(lines)


def _layer_places(world: World, kind: str, name: str) -> str:
    """
    Places on a realm/timeline — same mini-table polish as layer list:

      CODE          NAME              INSTANCE              REALM     TIMELINE
      ------------  ----------------  --------------------  --------  --------
      PLC-001-0001  Soft Landing      (inst_…)              Woven     Told-Time
    """
    layer = world.resolve_layer(kind, name)
    if layer is None:
        return fmt.err(f"No {kind} matching {name!r}.")
    if kind == "timeline":
        places = world.places_on_timeline(layer.id)
    else:
        places = world.places_in_realm(layer.id)

    layer_code = (getattr(layer, "ven_code", None) or "").strip()
    title = f"{kind} · {display_name(layer.name)}"
    if layer_code:
        title = f"{title}  ·  {layer_code}"

    if not places:
        return "\n".join(
            [
                fmt.title_line(title, kind=kind),
                fmt.hint(f"layer instance {layer.id}"),
                "",
                fmt.hint("No places on this layer yet."),
            ]
        )

    # Plain columns for width calc
    rows: list[tuple[str, str, str, str, str]] = []
    for p in places:
        ref = world.short_ref_of(p.id)
        pname = display_name(p.name)
        iid = f"({p.id})"
        coords = world.coords_of(p)
        rname = display_name(coords.get("realm_name") or "—")
        tname = display_name(coords.get("timeline_name") or "—")
        rows.append((ref, pname, iid, rname, tname))

    w_code = max(4, max(len(r[0]) for r in rows), len("CODE"))
    w_name = max(4, max(len(r[1]) for r in rows), len("NAME"))
    w_id = max(8, max(len(r[2]) for r in rows), len("INSTANCE"))
    w_realm = max(5, max(len(r[3]) for r in rows), len("REALM"))
    w_tl = max(8, max(len(r[4]) for r in rows), len("TIMELINE"))
    gap = "  "

    header = (
        f"  [dim]{fmt.safe(fmt.pad_visible('CODE', w_code))}{gap}"
        f"{fmt.safe(fmt.pad_visible('NAME', w_name))}{gap}"
        f"{fmt.safe(fmt.pad_visible('INSTANCE', w_id))}{gap}"
        f"{fmt.safe(fmt.pad_visible('REALM', w_realm))}{gap}"
        f"TIMELINE[/dim]"
    )
    rule = (
        f"  [dim]{'-' * w_code}{gap}"
        f"{'-' * w_name}{gap}"
        f"{'-' * w_id}{gap}"
        f"{'-' * w_realm}{gap}"
        f"{'-' * w_tl}[/dim]"
    )

    lines = [
        fmt.title_line(title, kind=kind),
        fmt.hint(f"layer instance {layer.id}"),
        "",
        fmt.section("Places"),
        header,
        rule,
    ]
    for ref, pname, iid, rname, tname in rows:
        lines.append(
            f"  [dim]{fmt.safe(fmt.pad_visible(ref, w_code))}[/dim]{gap}"
            f"{fmt.colored_padded_name(pname, 'place', w_name)}{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(iid, w_id))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(rname, w_realm))}[/dim]{gap}"
            f"[dim]{fmt.safe(fmt.pad_visible(tname, w_tl))}[/dim]"
        )
    lines.append("")
    lines.append(
        fmt.hint(
            f"{kind} set <name>  ·  {kind} places <name>  ·  look  ·  go …"
        )
    )
    return "\n".join(lines)


def _layer_assign(
    world: World,
    kind: str,
    *,
    layer_name: str | None = None,
    target_name: str | None = None,
    clear: bool = False,
) -> str:
    # resolve target instance
    if target_name:
        thing = world.resolve_here_named(target_name)
        if thing is None:
            # try place instances by name globally (unique)
            matches = world.find_instances_by_name(target_name, kind="place")
            if len(matches) == 1:
                thing = matches[0]
            elif not matches:
                return fmt.err(f"No {target_name!r} here (or unique place).")
            else:
                return fmt.err(f"Ambiguous {target_name!r}.")
    else:
        thing = world.player_location()
        if thing is None:
            return fmt.hint("Nowhere.")

    layer_id: str | None
    if clear:
        layer_id = None
        label = "—"
    else:
        assert layer_name is not None
        layer = world.resolve_layer(kind, layer_name)
        if layer is None:
            return fmt.err(
                f"No {kind} matching {layer_name!r}.  "
                f"Use: {kind} list  or  {kind} create {layer_name}"
            )
        layer_id = layer.id
        label = layer.name

    # capture prior coords for undo
    before = world.get_instance(thing.id)
    assert before is not None
    prior_layer = (
        before.timeline_instance_id if kind == "timeline" else before.realm_instance_id
    )
    loc = world.player_location()
    pid = world.player_id()
    sync_player = bool(pid and loc and thing.id == loc.id)
    prior_player_layer: str | None = None
    if sync_player and pid:
        player = world.get_instance(pid)
        if player:
            prior_player_layer = (
                player.timeline_instance_id
                if kind == "timeline"
                else player.realm_instance_id
            )

    if kind == "timeline":
        world.set_instance_coords(thing.id, timeline_instance_id=layer_id)
    else:
        world.set_instance_coords(thing.id, realm_instance_id=layer_id)

    # keep player avatar coords in sync when assigning the place you're in
    if sync_player and pid:
        if kind == "timeline":
            world.set_instance_coords(pid, timeline_instance_id=layer_id)
        else:
            world.set_instance_coords(pid, realm_instance_id=layer_id)

    def undo_assign(
        w: World,
        tid=thing.id,
        k=kind,
        pl=prior_layer,
        do_player=sync_player,
        pplayer=pid,
        ppl=prior_player_layer,
    ) -> None:
        if k == "timeline":
            w.set_instance_coords(tid, timeline_instance_id=pl)
            if do_player and pplayer:
                w.set_instance_coords(pplayer, timeline_instance_id=ppl)
        else:
            w.set_instance_coords(tid, realm_instance_id=pl)
            if do_player and pplayer:
                w.set_instance_coords(pplayer, realm_instance_id=ppl)

    world.undo_stack.push(f"{kind} {'clear' if clear else 'set'}", undo_assign)

    coords = world.coords_of(world.get_instance(thing.id))  # type: ignore[arg-type]
    action = "cleared" if clear else "set"
    from .ids import display_name

    shown_label = display_name(label) if label != "—" else "—"
    return fmt.join_blocks(
        fmt.ok(
            f"{kind} {action} · {display_name(thing.name)} → {shown_label}"
        ),
        fmt.hint(f"coords {_coords_label(coords)}"),
        gap=0,
    )
