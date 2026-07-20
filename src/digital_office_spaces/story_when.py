"""Story-when along timeline nodes: @N / @unknown (not craft created_at)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World

# Trailing: when @3  ·  when @unknown
_STORY_WHEN_SUFFIX_RE = re.compile(
    r"\s+when\s+@(?P<body>\d+|unknown)\s*$",
    re.IGNORECASE,
)

# Bare mythic lore stamp that is only @N / @unknown
_STORY_WHEN_ONLY_RE = re.compile(
    r"^@(?P<body>\d+|unknown)$",
    re.IGNORECASE,
)


def normalize_story_when(raw: str | None) -> tuple[str, int | None]:
    """
    Return (story_when token, node_index|None).

    Tokens are always ``@N`` or ``@unknown``.
    """
    s = (raw or "").strip()
    if not s:
        return "@unknown", None
    m = _STORY_WHEN_ONLY_RE.match(s)
    if not m:
        # Freeform mythic stamp is not a node — still unknown structurally
        return "@unknown", None
    body = m.group("body").lower()
    if body == "unknown":
        return "@unknown", None
    return f"@{int(body)}", int(body)


def peel_story_when_suffix(text: str) -> tuple[str, str, int | None]:
    """
    Strip trailing ``when @N`` / ``when @unknown`` from a command tail.

    Also accepts a tail that is *only* ``when @N`` (no leading space).

    Returns (remaining_text, story_when, node_index).
    """
    s = text or ""
    only = re.match(
        r"^when\s+@(?P<body>\d+|unknown)\s*$",
        s.strip(),
        re.IGNORECASE,
    )
    if only:
        body = only.group("body").lower()
        if body == "unknown":
            return "", "@unknown", None
        n = int(body)
        return "", f"@{n}", n
    m = _STORY_WHEN_SUFFIX_RE.search(s)
    if not m:
        return s.strip(), "@unknown", None
    remaining = s[: m.start()].rstrip()
    body = m.group("body").lower()
    if body == "unknown":
        return remaining, "@unknown", None
    n = int(body)
    return remaining, f"@{n}", n


# Mid-command: --when 0  ·  -w @2  ·  --when=unknown
_WHEN_FLAG_RE = re.compile(
    r"(?:^|\s)(?:--when|-w)(?:=|\s+)(?P<body>@?\d+|unknown)(?=\s|$)",
    re.IGNORECASE,
)


def peel_when_anywhere(text: str) -> tuple[str, str, int | None]:
    """
    Strip story when from trailing ``when @N`` **or** ``--when N`` / ``-w N``.

    Default story when is ``@unknown`` (not the item's create time — each
    movement is its own craft row with its own created_at).
    """
    from .argflags import story_when_from_flag

    s = text or ""
    s, sw, ni = peel_story_when_suffix(s)
    m = _WHEN_FLAG_RE.search(s)
    if m:
        sw, ni = story_when_from_flag(m.group("body"))
        s = (s[: m.start()] + " " + s[m.end() :]).strip()
        s = re.sub(r"\s+", " ", s)
    return s, sw, ni


def story_when_from_lore_label(when_label: str | None) -> tuple[str, int | None]:
    """If lore when is exactly @N / @unknown, use it; else @unknown."""
    return normalize_story_when(when_label)


def format_history_line(
    *,
    verb: str,
    story_when: str,
    crafted_at: str,
    realm_name: str | None,
    timeline_name: str | None,
    note: str = "",
    event_code: str = "",
    place_name: str | None = None,
) -> str:
    """
    Two-line history entry for narrow (≈72) columns.

    Line 1 — what: ``HST-004  ·  put  ·  into Keeper [interior]``
    Line 2 — when/where meta (caller typically dims + indents)::

        story @3  ·  Herenow  ·  Base / Start  ·  craft 2026-…
    """
    p = (place_name or "").strip() or "—"
    r = (realm_name or "").strip() or "—"
    t = (timeline_name or "").strip() or "—"
    code = (event_code or "").strip() or "—"
    event = (verb or "record").strip() or "record"
    explain = (note or "").strip() or "—"
    primary = f"{code}  ·  {event}  ·  {explain}"
    meta = (
        f"story {story_when or '@unknown'}  ·  {p}  ·  {r} / {t}  ·  "
        f"craft {crafted_at or '—'}"
    )
    return f"{primary}\n{meta}"


def resolve_strand_for_record(
    world: World,
    *,
    realm_instance_id: str | None = None,
    timeline_instance_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Prefer explicit ids; else player's current place layers."""
    if realm_instance_id or timeline_instance_id:
        return realm_instance_id, timeline_instance_id
    loc = world.player_location()
    if loc is None:
        return None, None
    return loc.realm_instance_id, loc.timeline_instance_id


def resolve_history_where(
    world: World,
    *,
    place_instance_id: str | None = None,
    realm_instance_id: str | None = None,
    timeline_instance_id: str | None = None,
) -> dict[str, str | None]:
    """
    Resolve place + realm + timeline ids and display names for a history row.

    Prefer explicit ids; fill gaps from the player's current location.
    Names are snapshots of *current* titles at record time (call once per act).
    """
    from .ids import display_name

    loc = world.player_location()
    place_id = place_instance_id
    realm_id = realm_instance_id
    tl_id = timeline_instance_id
    if loc is not None:
        if not place_id:
            place_id = loc.id
        if not realm_id:
            realm_id = loc.realm_instance_id
        if not tl_id:
            tl_id = loc.timeline_instance_id

    def _name(iid: str | None) -> str:
        if not iid:
            return ""
        inst = world.get_instance(iid)
        if inst is None:
            return ""
        return display_name(inst.name)

    return {
        "place_instance_id": place_id,
        "place_name": _name(place_id),
        "realm_instance_id": realm_id,
        "realm_name": _name(realm_id),
        "timeline_instance_id": tl_id,
        "timeline_name": _name(tl_id),
    }
