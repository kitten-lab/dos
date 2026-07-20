"""Local multiverse map: depth-limited exit tree from a place."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import format as fmt
from .ids import display_name

if TYPE_CHECKING:
    from .world import World

DEFAULT_MAP_DEPTH = 2
MAX_MAP_DEPTH = 4


@dataclass
class MapBranch:
    """One exit from a place and the subtree rooted at its destination."""

    label: str
    link_type: str
    dest_id: str
    dest_name: str
    dest_kind: str
    children: list["MapBranch"] = field(default_factory=list)
    # True if dest was already visited (cycle) or depth exhausted without expanding
    truncated: bool = False
    cycle: bool = False


@dataclass
class MapTree:
    root_id: str
    root_name: str
    root_kind: str
    depth: int
    branches: list[MapBranch]


def collect_map_tree(
    world: "World",
    root_id: str,
    *,
    depth: int = DEFAULT_MAP_DEPTH,
) -> MapTree:
    """
    Build an exit tree from ``root_id`` up to ``depth`` hops.

    Depth 0 = root only (no exits listed). Depth 1 = direct exits.
    Cycles are marked; already-seen places are not re-expanded.
    """
    depth = max(0, min(int(depth), MAX_MAP_DEPTH))
    root = world.get_instance(root_id)
    if root is None:
        raise ValueError(f"No instance {root_id}")

    def expand(node_id: str, remaining: int, seen: set[str]) -> list[MapBranch]:
        if remaining <= 0:
            return []
        out: list[MapBranch] = []
        for ex in world.exits(node_id):
            dest_id = ex["to_instance_id"]
            dest = world.get_instance(dest_id)
            dname = display_name(dest.name) if dest else "?"
            dkind = dest.ven_kind if dest else "place"
            label = ex["label"] or "?"
            ltype = ex["link_type"] or "spatial"
            if dest_id in seen:
                out.append(
                    MapBranch(
                        label=label,
                        link_type=ltype,
                        dest_id=dest_id,
                        dest_name=dname,
                        dest_kind=dkind,
                        children=[],
                        truncated=True,
                        cycle=True,
                    )
                )
                continue
            child_seen = set(seen)
            child_seen.add(dest_id)
            kids: list[MapBranch] = []
            trunc = False
            if remaining > 1:
                kids = expand(dest_id, remaining - 1, child_seen)
            else:
                # at last hop: show edge but note more may exist
                if world.exits(dest_id):
                    trunc = True
            out.append(
                MapBranch(
                    label=label,
                    link_type=ltype,
                    dest_id=dest_id,
                    dest_name=dname,
                    dest_kind=dkind,
                    children=kids,
                    truncated=trunc and not kids,
                    cycle=False,
                )
            )
        return out

    seen_root = {root_id}
    branches = expand(root_id, depth, seen_root)
    return MapTree(
        root_id=root_id,
        root_name=display_name(root.name),
        root_kind=root.ven_kind,
        depth=depth,
        branches=branches,
    )


def format_map_tree(tree: MapTree) -> str:
    """Rich markup tree: link types colored, place names by kind."""
    lines: list[str] = [
        fmt.section("Map"),
        (
            f"{fmt.colored_name(tree.root_name, tree.root_kind)}  "
            f"[dim](here · depth {tree.depth})[/dim]"
        ),
    ]
    if tree.depth <= 0:
        lines.append(fmt.hint("Depth 0 — only this place.  Try: map 1  or  map 2"))
        return "\n".join(lines)
    if not tree.branches:
        lines.append(fmt.hint("No paths from here."))
        return "\n".join(lines)

    def render_branch(branch: MapBranch, prefix: str, is_last: bool) -> None:
        joint = "└─" if is_last else "├─"
        type_mk = fmt.link_type_markup(branch.link_type)
        dest_mk = fmt.colored_name(branch.dest_name, branch.dest_kind)
        extra = ""
        if branch.cycle:
            extra = "  [dim](cycle)[/dim]"
        elif branch.truncated:
            extra = "  [dim](…)[/dim]"
        lines.append(
            f"{prefix}{joint} {fmt.safe(branch.label)}  "
            f"({type_mk})  →  {dest_mk}{extra}"
        )
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(branch.children):
            render_branch(child, child_prefix, i == len(branch.children) - 1)

    for i, br in enumerate(tree.branches):
        render_branch(br, "", i == len(tree.branches) - 1)

    lines.append(
        fmt.hint(
            f"Link colors: spatial · dimensional · temporal · narrative · conditional  "
            f"·  map <1–{MAX_MAP_DEPTH}> for depth"
        )
    )
    return "\n".join(lines)


def parse_map_args(arg: str) -> tuple[int, str | None]:
    """
    Parse map command args → (depth, error_hint).

    Accepts empty, a single depth digit, or ``here`` / ``here <n>``.
    """
    arg = (arg or "").strip()
    if not arg:
        return DEFAULT_MAP_DEPTH, None
    parts = arg.split()
    if parts[0].lower() in ("here", "local", "."):
        parts = parts[1:]
        if not parts:
            return DEFAULT_MAP_DEPTH, None
    if len(parts) == 1 and parts[0].isdigit():
        d = int(parts[0])
        if d < 0 or d > MAX_MAP_DEPTH:
            return DEFAULT_MAP_DEPTH, (
                f"Map depth must be 0–{MAX_MAP_DEPTH} (default {DEFAULT_MAP_DEPTH})."
            )
        return d, None
    return DEFAULT_MAP_DEPTH, (
        f"Usage: map  ·  map <depth 0–{MAX_MAP_DEPTH}>  ·  map here [depth]"
    )
