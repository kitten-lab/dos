"""Dump dos help topics into a Kitten-Lab folio + optional .ven pack.

Usage:
  python scripts/dump_help_to_folio.py
  python scripts/dump_help_to_folio.py --world C:\\Builds\\Kitten-Lab --export
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow running from repo root without install
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dos.db import connect, get_meta  # noqa: E402
from dos.format import plain  # noqa: E402
from dos.help_topics import (  # noqa: E402
    _HELP_INDEX_CATEGORIES,
    _init_topics,
    _TOPICS,
    render_help_index,
    render_help_topic,
    resolve_topic,
    topic_index_entries,
)
from dos.world import World  # noqa: E402


def _topic_keys_in_order() -> list[tuple[str, str]]:
    """(leaf_title, topic_key) covering index + any orphan topics."""
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for _code, term, _summary, cat in topic_index_entries():
        key = resolve_topic(term.split("/")[0].strip()) or resolve_topic(term)
        if key is None:
            # multi-label index rows
            for part in re.split(r"[/,]", term):
                key = resolve_topic(part.strip())
                if key:
                    break
        if key and key not in seen:
            seen.add(key)
            ordered.append((f"{cat} · {term}", key))
    _init_topics()
    for key in sorted(_TOPICS.keys()):
        if key not in seen:
            ordered.append((f"extra · {key}", key))
            seen.add(key)
    return ordered


def build_pages() -> list[tuple[str, str]]:
    """(title, plain body) pages for the folio."""
    pages: list[tuple[str, str]] = []
    # 0. Index / cheat sheet
    index_body = plain(render_help_index())
    pages.append(
        (
            "00 · Index",
            (
                "STUDIO Writer / World Studio command help — dumped from help_topics.\n"
                "Each leaf is one help topic (plain text; markup stripped).\n"
                "\n"
                + index_body
            ),
        )
    )
    for i, (label, key) in enumerate(_topic_keys_in_order(), start=1):
        body = plain(render_help_topic(key))
        title = f"{i:02d} · {key}"
        # Keep title short for folio chrome; full label in body header
        pages.append((title, f"[{label}]\n\n{body}"))
    return pages


def put_in_world(world_path: Path, pages: list[tuple[str, str]]) -> tuple[str, str]:
    """Create or replace 'World Studio Help' folio in *world_path*. Returns (ven_id, inst_id)."""
    conn = connect(world_path)
    w = World(conn)
    loc = w.player_location()
    if loc is None:
        raise SystemExit("No player location in world — open it once or set player.")

    # Reuse existing help folio if present
    existing = None
    for c in w.resolve_here_candidates():
        if (c.ven_kind or "").lower() in ("folio", "book") and "world studio help" in (
            c.name or ""
        ).lower():
            existing = c
            break
    if existing is None:
        # global search by name
        found = w.find_instances_by_name("World Studio Help", kind="folio")
        if not found:
            found = w.find_instances_by_name("World Studio Help", kind="book")
        if found:
            existing = found[0]

    if existing is not None:
        inst_id = existing.id
        ven_id = existing.ven_id
        conn.execute(
            "DELETE FROM book_pages WHERE book_instance_id = ?", (inst_id,)
        )
        conn.commit()
        cont = w.container_of(inst_id)
        if not cont or cont[0] != loc.id:
            w.put_in(inst_id, loc.id, slot="interior")
    else:
        ven_id = w.create_ven(
            "World Studio Help",
            "folio",
            (
                "Full command help dump from dos (help_topics). "
                "Reference folio for builders in Kitten-Lab."
            ),
            tags=["help", "reference", "studio"],
        )
        inst_id = w.instantiate(ven_id)
        if not isinstance(inst_id, str):
            inst_id = inst_id.id  # type: ignore[attr-defined]
        w.put_in(inst_id, loc.id, slot="interior")
        w.set_book_incomplete(inst_id, False)

    for title, body in pages:
        w.add_book_page(inst_id, title, body)

    w.set_book_incomplete(inst_id, False)
    return ven_id, inst_id


def export_ven_pack(world: World, inst_id: str, *, origin: str) -> Path:
    from dos.ven_pack import export_instance, ven_collector_dir

    inst = world.get_instance(inst_id)
    if inst is None:
        raise SystemExit(f"No instance {inst_id}")
    return export_instance(
        world,
        inst,
        origin_world=origin,
        collector=ven_collector_dir(),
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--world",
        type=Path,
        default=Path(r"C:\Builds\Kitten-Lab"),
        help="World SQLite path (default: Kitten-Lab)",
    )
    p.add_argument(
        "--export",
        action="store_true",
        help="Also write a .ven pack into ~/.aidm/ven-collector",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print page count and first titles only",
    )
    args = p.parse_args()
    pages = build_pages()
    print(f"pages: {len(pages)}")
    for t, b in pages[:5]:
        print(f"  · {t}  ({len(b)} chars)")
    if args.dry_run:
        return

    ven_id, inst_id = put_in_world(args.world, pages)
    print(f"folio in {args.world}")
    print(f"  ven={ven_id}  inst={inst_id}")
    print(f"  leaves={len(pages)}")

    if args.export:
        conn = connect(args.world)
        w = World(conn)
        origin = (get_meta(conn, "world_name") or "Kitten-Lab").strip()
        path = export_ven_pack(w, inst_id, origin=origin)
        print(f"exported: {path}")


if __name__ == "__main__":
    main()
