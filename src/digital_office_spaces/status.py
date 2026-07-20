"""Player situation snapshot for locate self (and strip / sidebar helpers)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import format as fmt
from .ids import display_name

if TYPE_CHECKING:
    from .world import World

# Panel title for format_sidebar (tests / optional UI)
SIDEBAR_TITLE = "locate"


@dataclass
class Situation:
    who: str
    place: str
    realm: str
    timeline: str
    coords: str
    inv_count: int
    exit_count: int
    place_id: str | None
    player_id: str | None
    inventory_names: list[str]
    place_ven_label: str = "—"
    realm_id: str | None = None
    timeline_id: str | None = None
    player_layer_note: str | None = None

    @property
    def nowhere(self) -> bool:
        return self.place_id is None


def _coords_display(realm_name: str, timeline_name: str) -> str:
    r = display_name(realm_name) if realm_name and realm_name != "—" else "—"
    t = display_name(timeline_name) if timeline_name and timeline_name != "—" else "—"
    return f"{r} / {t}"


def situation(world: World) -> Situation:
    """Snapshot of who / place / layers / inventory for locate self and strip."""
    pid = world.player_id()
    player = world.get_instance(pid) if pid else None
    inv = world.inventory() if pid else []
    inv_names = [display_name(it.name) for it in inv]
    loc = world.player_location()
    if loc is None:
        return Situation(
            who=display_name(player.name) if player else "—",
            place="—",
            realm="—",
            timeline="—",
            coords="— / —",
            inv_count=len(inv),
            exit_count=0,
            place_id=None,
            player_id=pid,
            inventory_names=inv_names,
        )
    coords = world.coords_of(loc)
    exits = world.exits(loc.id)
    realm_n = coords["realm_name"]
    tl_n = coords["timeline_name"]
    ven_label = f"{display_name(loc.ven_name)} ({loc.ven_slug})"
    layer_note = None
    if player is not None:
        pcoords = world.coords_of(player)
        if (
            player.realm_instance_id != loc.realm_instance_id
            or player.timeline_instance_id != loc.timeline_instance_id
        ):
            layer_note = (
                f"your avatar layer: {pcoords['label']}  "
                f"(place layer may differ until you timeline set / realm set)"
            )
    return Situation(
        who=display_name(player.name) if player else "—",
        place=display_name(loc.name),
        realm=display_name(realm_n) if realm_n != "—" else "—",
        timeline=display_name(tl_n) if tl_n != "—" else "—",
        coords=_coords_display(realm_n, tl_n),
        inv_count=len(inv),
        exit_count=len(exits),
        place_id=loc.id,
        player_id=pid,
        inventory_names=inv_names,
        place_ven_label=ven_label,
        realm_id=loc.realm_instance_id,
        timeline_id=loc.timeline_instance_id,
        player_layer_note=layer_note,
    )


def format_sidebar(world: World) -> str:
    """Multi-line panel helper (same fields as locate self; tests / optional UI)."""
    s = situation(world)
    lines = [
        f"[bold {fmt.ACCENT}]{SIDEBAR_TITLE}[/bold {fmt.ACCENT}]",
        "",
        f"[dim]character[/dim]",
        f"  [bold]{fmt.colored_name(s.who, 'person')}[/bold]",
        "",
        f"[dim]location[/dim]",
        f"  [bold]{fmt.colored_name(s.place, 'place')}[/bold]",
        f"  [dim]realm[/dim]  {fmt.colored_name(s.realm, 'realm')}",
        f"  [dim]time[/dim]   {fmt.colored_name(s.timeline, 'timeline')}",
        f"  [{fmt.ACCENT}]{fmt.safe(s.coords)}[/{fmt.ACCENT}]",
        f"  [dim]paths[/dim]  {s.exit_count}",
        "",
        f"[dim]inventory[/dim]  ({s.inv_count})",
    ]
    if s.inventory_names:
        for name in s.inventory_names[:12]:
            lines.append(f"  [dim]·[/dim] {fmt.safe(name)}")
        if len(s.inventory_names) > 12:
            lines.append(f"  [dim]… +{len(s.inventory_names) - 12} more[/dim]")
    else:
        lines.append("  [dim](empty)[/dim]")
    if s.nowhere:
        lines.append("")
        lines.append("[dim](nowhere — dig or reseed)[/dim]")
    return "\n".join(lines)


def format_strip(world: World) -> str:
    """One-line strip for the Rich REPL above the prompt."""
    s = situation(world)
    return (
        f"[dim]you[/dim] [bold]{fmt.colored_name(s.who, 'person')}[/bold]  "
        f"[dim]@[/dim] [bold]{fmt.colored_name(s.place, 'place')}[/bold]  "
        f"[{fmt.ACCENT}]{fmt.safe(s.coords)}[/{fmt.ACCENT}]  "
        f"[dim]inv[/dim] {s.inv_count}  "
        f"[dim]paths[/dim] {s.exit_count}"
    )


def format_status_command(world: World) -> str:
    """
    Full situation block for ``locate self`` (avatar where-now).

    Name kept for import stability; prefer calling via the locate command.
    """
    s = situation(world)
    if s.nowhere:
        return fmt.join_blocks(
            fmt.title_line("Locate · self"),
            fmt.meta_row("you", s.who, kind="person"),
            fmt.hint("Nowhere — dig or reseed."),
            gap=0,
        )

    inv_line = ", ".join(s.inventory_names[:8]) if s.inventory_names else "(empty)"
    if len(s.inventory_names) > 8:
        inv_line += f" … +{len(s.inventory_names) - 8}"

    blocks: list[str] = [
        fmt.title_line("Locate · self"),
        fmt.meta_row("you", s.who, kind="person"),
        fmt.meta_row("place", s.place, s.place_id, kind="place"),
        fmt.meta_row("ven", s.place_ven_label),
        fmt.meta_row("realm", s.realm, s.realm_id, kind="realm"),
        fmt.meta_row("timeline", s.timeline, s.timeline_id, kind="timeline"),
        fmt.meta_row("coords", s.coords),
        fmt.meta_row("paths", str(s.exit_count)),
        fmt.meta_row("inventory", inv_line),
    ]
    if s.player_layer_note:
        blocks.append(fmt.hint(s.player_layer_note))
    return fmt.join_blocks(*blocks, gap=0)
