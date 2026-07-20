"""Wiki dossier: one screen of context for a real VEN or instance (not a book)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from . import format as fmt
from .ids import display_name
from .world import (
    COMPOSITION_DEPTH_DEEP,
    COMPOSITION_DEPTH_DEFAULT,
    CompositionNode,
    format_kind_label,
)

if TYPE_CHECKING:
    from .world import InstanceView, VenView, World

WikiStatus = Literal["instance", "ven", "ambiguous", "missing"]

# meta_json key for explicit sub-links (option B): list of target ven ids
WIKI_LINKS_KEY = "wiki_links"


def parse_deep_flag(arg: str) -> tuple[str, bool]:
    """
    Strip ``deep`` / ``--deep`` / ``-deep`` tokens from a query (any position).

    ``\"Elon deep\"`` → (``\"Elon\"``, True);
    ``\"--deep at box\"`` → (``\"at box\"``, True);
    ``\"deep\"`` alone → (``\"\"``, True).
    """
    raw = (arg or "").strip()
    if not raw:
        return "", False
    parts = raw.split()
    deep = False
    kept: list[str] = []
    for p in parts:
        pl = p.lower()
        if pl in ("deep", "--deep", "-deep"):
            deep = True
            continue
        kept.append(p)
    return " ".join(kept).strip(), deep


def format_composition_tree_lines(
    nodes: list[CompositionNode],
    *,
    prefix: str = "",
) -> list[str]:
    """
    Render composition like the map tree: ``├─`` / ``└─`` with ``│`` guides.

    Shared by wiki, compose, and examine.
    """
    lines: list[str] = []
    n = len(nodes)
    for i, node in enumerate(nodes):
        is_last = i == n - 1
        joint = "└─" if is_last else "├─"
        p = node.part
        name_mk = fmt.colored_name(display_name(p.part_name), p.part_kind or "other")
        role = p.role or "part"
        detail = f"{role}"
        if p.part_kind:
            detail += f"  ·  {p.part_kind}"
        if p.part_slug:
            detail += f"  ·  {p.part_slug}"
        extra = "  [dim](cycle)[/dim]" if node.is_cycle else ""
        lines.append(
            f"{prefix}{joint} {name_mk}  "
            f"[dim]({fmt.safe(detail)})[/dim]{extra}"
        )
        if node.children:
            child_prefix = prefix + ("   " if is_last else "│  ")
            lines.extend(
                format_composition_tree_lines(
                    node.children, prefix=child_prefix
                )
            )
    return lines


def composition_depth_for_deep(deep: bool) -> int:
    return COMPOSITION_DEPTH_DEEP if deep else COMPOSITION_DEPTH_DEFAULT


def _sublink_title(world: World, ven: VenView) -> str:
    """
    Player-facing name for a wiki sub-link target (always a prime).

    Links store prime ids. When that prime has exactly one lived instance, prefer
    the instance title so ``wiki link … Herenow`` does not display as bare
    ``Place place · PLC-001``.
    """
    insts = world.list_instances_of_ven(ven.id)
    if len(insts) == 1:
        return display_name(insts[0].name)
    return display_name(ven.name)


def _sublink_meta(world: World, ven: VenView) -> str:
    """kind[/subtype] · code  (+ prime name when title is a lived override)."""
    olab = format_kind_label(ven.kind, ven.subtype)
    code = (ven.code or ven.slug or "").strip()
    title = _sublink_title(world, ven)
    prime = display_name(ven.name)
    bits: list[str] = [olab]
    # When we show Herenow but the prime is Place, whisper the species once
    if title.casefold() != prime.casefold():
        bits.append(prime)
    if code:
        bits.append(code)
    return "  ·  ".join(bits)


@dataclass
class WikiTarget:
    """Resolved wiki target — only real primes or instances."""

    status: WikiStatus
    ven: VenView | None = None
    instance: InstanceView | None = None
    matches: list[Any] | None = None  # ambiguous: instances and/or vens
    message: str = ""


def resolve_wiki_target(world: World, label: str) -> WikiTarget:
    """
    Resolve ``label`` to a unique instance or VEN only.

    Order: unique here/inv → unique global instance → unique VEN → missing.
    Ambiguous at any step → ambiguous (no invented page).
    """
    key = (label or "").strip()
    if not key:
        return WikiTarget(status="missing", message="Name a VEN or instance.")

    # 1) here / inv
    here = world.resolve_here_matches(key)
    if len(here) == 1:
        inst = here[0]
        ven = world.get_ven(inst.ven_id)
        return WikiTarget(status="instance", instance=inst, ven=ven)
    if len(here) > 1:
        return WikiTarget(
            status="ambiguous",
            matches=here,
            message=f"Ambiguous {key!r} — {len(here)} matches here/inv.",
        )

    # 2) global instances by name
    global_hits = world.find_instances_by_name(key)
    if len(global_hits) == 1:
        inst = global_hits[0]
        ven = world.get_ven(inst.ven_id)
        return WikiTarget(status="instance", instance=inst, ven=ven)
    if len(global_hits) > 1:
        return WikiTarget(
            status="ambiguous",
            matches=global_hits,
            message=f"Ambiguous {key!r} — {len(global_hits)} instances world-wide.",
        )

    # 3) prime VEN
    ven = world.find_ven(key)
    if ven is not None:
        return WikiTarget(status="ven", ven=ven)

    return WikiTarget(
        status="missing",
        message=f"No VEN or instance matching {key!r}.  Links only open real entities.",
    )


def format_wiki_dossier(
    world: World,
    target: WikiTarget,
    *,
    deep: bool = False,
    include_title: bool = True,
) -> str:
    """One-screen dossier: identity, desc, tags, notes (lore), instances, sub-links.

    ``deep=True`` expands nested composition (see ``composition_tree``).
    ``include_title=False`` omits the bold Wiki title (soft reader header owns it).
    """
    if target.status == "missing":
        return fmt.err(target.message or "Not found.")
    if target.status == "ambiguous":
        lines = [
            fmt.err(target.message or "Ambiguous."),
            fmt.hint(
                "Qualify with inv / here / #FIELD-NOTES-0001, or a unique prime name."
            ),
        ]
        for m in target.matches or []:
            if hasattr(m, "ven_kind"):
                ref = world.short_ref_of(m.id)
                lines.append(
                    fmt.bullet(
                        m.name,
                        f"{m.ven_kind}  ·  #{ref}  ·  {world.where_label(m.id)}",
                        kind=m.ven_kind,
                    )
                )
            elif hasattr(m, "kind"):
                mlab = format_kind_label(m.kind, getattr(m, "subtype", None))
                lines.append(
                    fmt.bullet(m.name, f"VEN {mlab}  ·  {m.slug}", kind=m.kind)
                )
        return "\n".join(lines)

    ven = target.ven
    inst = target.instance
    if ven is None and inst is not None:
        ven = world.get_ven(inst.ven_id)
    if ven is None:
        return fmt.err("Missing VEN for wiki target.")

    kind_lab = format_kind_label(ven.kind, ven.subtype)
    title_name = display_name(inst.name) if inst else display_name(ven.name)
    blocks: list[str | None] = []
    if include_title:
        blocks.append(fmt.title_line(f"Wiki · {title_name}", kind=ven.kind))
    blocks.append(
        fmt.hint(
            f"{kind_lab}  ·  slug {ven.slug}  ·  {ven.id}"
            + (f"  ·  instance {inst.id}" if inst else "  ·  prime")
        )
    )

    # Description: instance override if dossier is instance-scoped, else VEN canon
    if inst is not None:
        desc = inst.description or ""
        desc_src = "instance" if world.get_description_override(inst.id) is not None else "VEN"
    else:
        desc = ven.description or ""
        desc_src = "VEN"
    blocks.append(fmt.section("Description"))
    blocks.append(fmt.prose(desc) if desc.strip() else fmt.hint("(no description)"))
    blocks.append(fmt.hint(f"source · {desc_src}"))

    # Tags
    tags = list(ven.tags or [])
    blocks.append(fmt.section("Tags"))
    if tags:
        blocks.append("  " + "  ".join(f"[dim]·[/dim] {fmt.safe(t)}" for t in tags))
    else:
        blocks.append(fmt.hint("(no tags)"))

    # Lineage (specialization)
    path = world.lineage_path(ven.id)
    if len(path) >= 2:
        blocks.append(fmt.section("Lineage"))
        blocks.append(fmt.hint(" › ".join(display_name(v.name) for v in path)))
    children = world.children_of(ven.id)
    if children:
        blocks.append(fmt.section("Specializations"))
        for ch in children:
            clab = format_kind_label(ch.kind, ch.subtype)
            blocks.append(
                fmt.bullet(
                    display_name(ch.name),
                    f"{clab}  ·  {ch.slug}",
                    kind=ch.kind,
                )
            )

    # Composition (prime parts; optional nested tree)
    depth = composition_depth_for_deep(deep)
    tree = world.composition_tree(ven.id, max_depth=depth)
    if tree:
        title = "Composed of" + (" (deep)" if deep else "")
        blocks.append(fmt.section(title))
        blocks.extend(format_composition_tree_lines(tree))
        if not deep and any(
            world.list_ven_parts(n.part.part_ven_id) for n in tree
        ):
            blocks.append(
                fmt.hint(
                    f"Nested parts: wiki {ven.slug} deep  ·  compose {ven.slug} deep"
                )
            )

    # Notes = lore (VEN always; instance lore too if instance-scoped)
    notes: list = list(world.lore_for("ven", ven.id))
    if inst is not None:
        notes = list(world.lore_for("instance", inst.id)) + notes
    blocks.append(fmt.section("Notes (lore)"))
    if not notes:
        blocks.append(
            fmt.hint(
                f"No lore yet.  lore ven {ven.slug} add Title | body"
                + (f"  ·  lore on <this copy> add …" if inst else "")
            )
        )
    else:
        # newest last in lore_for order is chronological; show last 12
        for r in notes[-12:]:
            title = r["title"] or "(untitled)"
            stamp = (r["when_label"] or "").strip()
            meta = f"when {stamp}" if stamp else "typed " + (r["created_at"] or "")
            blocks.append(fmt.bullet(title, meta))
            snippet = (r["body"] or "").strip().split("\n", 1)[0][:100]
            if snippet:
                blocks.append(f"      [dim]{fmt.safe(snippet)}[/dim]")

    # Instances of this prime
    insts = world.list_instances_of_ven(ven.id)
    blocks.append(fmt.section("Instances"))
    if not insts:
        blocks.append(fmt.hint(f"(none)  ·  spawn {ven.slug}"))
    else:
        for i in insts:
            ref = world.short_ref_of(i.id)
            where = world.where_label(i.id)
            mark = "  ← this" if inst and i.id == inst.id else ""
            blocks.append(
                fmt.bullet(
                    i.name,
                    f"#{ref}  ·  {where}{mark}",
                    kind=i.ven_kind,
                )
            )

    # Sub-links from meta_json.wiki_links (ven ids — always primes)
    link_ids = world.get_wiki_links(ven.id)
    blocks.append(fmt.section("Sub-links"))
    if not link_ids:
        blocks.append(
            fmt.hint(
                f"None.  wiki link {ven.slug} <other ven|instance>  "
                f"·  wiki unlink …"
            )
        )
    else:
        for lid in link_ids:
            other = world.get_ven(lid)
            if other is None:
                blocks.append(fmt.hint(f"  ·  (missing ven {lid})"))
                continue
            blocks.append(
                fmt.bullet(
                    _sublink_title(world, other),
                    _sublink_meta(world, other),
                    kind=other.kind,
                )
            )

    # Book hint
    if (ven.kind or "").lower() in ("folio", "book"):
        open_name = display_name(inst.name) if inst else display_name(ven.name)
        blocks.append(
            fmt.hint(
                f"This is a book VEN — read pages with:  book open {open_name}"
            )
        )
    else:
        blocks.append(
            fmt.hint(
                "Situated play: examine / go  ·  "
                "Write [[…]] in studio text; open with wiki <name>"
            )
        )

    return fmt.join_blocks(*blocks, gap=1)
