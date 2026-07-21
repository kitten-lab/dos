"""Temporary Data Fragments — printed tickets (slips), not full VEN primes."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# Range separators in free text: "Jan 20 - Feb 15 2026"
_RANGE_SPLIT = re.compile(
    r"\s+[-–—]\s+|\s+to\s+|\s+through\s+|\s+thru\s+",
    re.IGNORECASE,
)

# Ticket subtypes (calendar / office)
TICKET_SUBTYPES = frozenset(
    {"date", "label", "note", "tag", "assignment"}
)
# Aliases accepted on -t / print ass → stored as assignment
TICKET_SUBTYPE_ALIASES: dict[str, str] = {
    "ass": "assignment",
    "assign": "assignment",
    "staff": "assignment",
    "assignment": "assignment",
}
# Glance order in look lists (date first — calendars; then staff slips)
TICKET_SUBTYPE_ORDER: tuple[str, ...] = (
    "date",
    "assignment",
    "label",
    "note",
    "tag",
)
# Ticket kinds (due / state semantics) — assignment -k is free text, not these
TICKET_KINDS = frozenset({"range", "due", "state", "point", "open"})

# Presence brick colors (white text on this background) — by subtype
TICKET_BRICK_COLORS: dict[str, str] = {
    "date": "#5ec8d8",  # cyan — calendars / deadlines
    "assignment": "#eab308",  # amber — staff assignment (person)
    "note": "#d4a574",  # warm gold — scribbles
    "label": "#c084fc",  # soft purple — tags
    "tag": "#4ade80",  # green
}
# Date-ticket brick tint by calendar phase (overrides subtype cyan)
TICKET_PHASE_BRICK_COLORS: dict[str, str] = {
    "ACTIVE": "#22c55e",  # green — in window now
    "OVER": "#6b7280",  # slate — past
    "NEXT": "#22d3ee",  # bright cyan — soonest upcoming
}
# Long note/label bricks get truncated for the row chip
TICKET_BRICK_MAX_LEN = 28


def canonical_ticket_subtype(raw: str | None) -> str:
    """Map aliases (ass, staff, …) to stored subtype; default empty."""
    key = (raw or "").strip().lower()
    if not key:
        return ""
    return TICKET_SUBTYPE_ALIASES.get(key, key)


def is_assignment_subtype(raw: str | None) -> bool:
    return canonical_ticket_subtype(raw) == "assignment"


def ticket_data_display(
    data: dict[str, Any] | None,
    *,
    subtype: str | None = None,
) -> str:
    """
    Human brick face from tdf_data.

    Date → range / day. Assignment → **person name only** (never role, never
    the word ass/assignment). Else note body.
    """
    d = data or {}
    if is_assignment_subtype(subtype) or d.get("person_ven_id") or d.get(
        "person_name"
    ):
        person = (d.get("person_name") or "").strip()
        if person:
            return person
        # Do not fall through to raw/query junk or subtype aliases
        return "—"
    start = (d.get("start") or "").strip()
    end = (d.get("end") or "").strip()
    if start and end:
        return f"{start} → {end}"
    if start:
        return start
    return (d.get("raw") or d.get("when") or "").strip()


def ticket_staff_kind(data: dict[str, Any] | None, kind: str | None = None) -> str:
    """
    Free-form staffer role for assignment slips (lead col1 = -k).

    Prefer staff_kind; ignore payload kind values that are ticket subtypes
    (ass / assignment / date / …).
    """
    d = data or {}
    for key in ("staff_kind", "role"):
        v = (d.get(key) or "").strip()
        if v:
            return v
    # data["kind"] may be the staff role for assignment slips
    dk = (d.get("kind") or "").strip()
    if dk and not is_assignment_subtype(dk) and dk.lower() not in TICKET_SUBTYPES:
        return dk
    k = (kind or "").strip()
    if k and not is_assignment_subtype(k) and k.lower() not in TICKET_SUBTYPES:
        return k
    return ""


def ticket_brick_face(
    subtype: str | None,
    data: dict[str, Any] | None = None,
    *,
    data_display: str | None = None,
) -> str:
    """
    Visible brick *label* (no markup): the due-date bits / person name.

    Date slips → ``Jan 20 → Feb 15`` or ``2026-07-21``.
    Assignment → person name only (never ``ASS`` / role).
    Notes/labels → raw body.
    """
    if data_display is not None:
        body = data_display.strip()
    else:
        body = ticket_data_display(data, subtype=subtype).strip()
    if not body:
        if is_assignment_subtype(subtype):
            body = "—"
        else:
            # Never surface command aliases (ass) on the brick
            sub = canonical_ticket_subtype(subtype) or (subtype or "ticket")
            if sub.lower() in ("ass", "assign"):
                sub = "ticket"
            body = sub.strip().upper() or "TICKET"
    if len(body) > TICKET_BRICK_MAX_LEN:
        body = body[: TICKET_BRICK_MAX_LEN - 1] + "…"
    return f" {body} "


def ticket_brick_plain(
    subtype: str | None = None,
    data: dict[str, Any] | None = None,
    *,
    data_display: str | None = None,
) -> str:
    """Plain width of the data brick (alias of :func:`ticket_brick_face`)."""
    return ticket_brick_face(subtype, data, data_display=data_display)


def ticket_brick_color(
    subtype: str | None,
    phase: str | None = None,
) -> str:
    """
    Background color for the data brick.

    Date slips: phase tint when ACTIVE / OVER / NEXT; else subtype cyan.
    Other subtypes keep their glance color.
    """
    ph = (phase or "").strip().upper()
    if ph in TICKET_PHASE_BRICK_COLORS:
        return TICKET_PHASE_BRICK_COLORS[ph]
    key = (subtype or "").strip().lower()
    return TICKET_BRICK_COLORS.get(key, "#6b7280")


def ticket_brick_markup(
    subtype: str | None,
    data: dict[str, Any] | None = None,
    *,
    data_display: str | None = None,
    phase: str | None = None,
) -> str:
    """White-on-color brick whose face is the due-date / payload bits."""
    face = ticket_brick_face(subtype, data, data_display=data_display)
    color = ticket_brick_color(subtype, phase)
    # face already has leading/trailing spaces
    return f"[bold white on {color}]{face}[/]"


def ticket_subtype_rank(subtype: str | None) -> int:
    """Sort rank for ticket subtype (date first). Unknown types after known."""
    key = (subtype or "").strip().lower()
    try:
        return TICKET_SUBTYPE_ORDER.index(key)
    except ValueError:
        return len(TICKET_SUBTYPE_ORDER)


def parse_ticket_date_token(raw: str) -> date | None:
    """
    Best-effort parse of a ticket date token for ordering.

    Accepts ISO (2026-07-21), US (7/21/2026), and a few month-name forms.
    Returns None when unparseable (those sort last among date tickets).
    """
    s = (raw or "").strip()
    if not s:
        return None
    # Take the start of a range if someone stuffed "a → b" in one field
    if "→" in s:
        s = s.split("→", 1)[0].strip()
    if " - " in s or " – " in s:
        s = re.split(r"\s+[-–]\s+", s, maxsplit=1)[0].strip()

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d/%m/%Y",
        "%b %d %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Month + day without year → this calendar year (ordering only)
    for fmt in ("%b %d", "%B %d", "%m/%d"):
        try:
            d = datetime.strptime(s, fmt)
            today = date.today()
            return date(today.year, d.month, d.day)
        except ValueError:
            continue
    return None


def ticket_date_sort_key(data: dict[str, Any] | None) -> tuple[int, date | str]:
    """
    Sort key for date tickets: (0, parsed_date) or (1, raw_string) if unparsed.

    Earlier dates first. Empty / unparseable last (then lexicographic raw).
    """
    d = data or {}
    start = (d.get("start") or d.get("when") or d.get("raw") or "").strip()
    parsed = parse_ticket_date_token(start)
    if parsed is not None:
        return (0, parsed)
    # unparseable / empty — after real dates; still group by text
    return (1, start.casefold() if start else "\uffff")


def ticket_list_sort_key(
    subtype: str | None,
    data: dict[str, Any] | None,
    *,
    name: str = "",
    code: str = "",
) -> tuple:
    """
    Full sort key for a ticket in look / examine lists::

      subtype rank · date (date tickets) · name · code
    """
    sub = (subtype or "").strip().lower()
    rank = ticket_subtype_rank(sub)
    if sub == "date":
        dkey = ticket_date_sort_key(data)
    else:
        # Non-date: stable secondary by display data then name
        dkey = (2, ticket_data_display(data).casefold())
    return (rank, dkey, (name or "").casefold(), (code or "").casefold())


def ticket_date_bounds(
    data: dict[str, Any] | None,
) -> tuple[date | None, date | None]:
    """
    Parsed (start, end) for a date ticket.

    Point / due slips: end defaults to start. Ranges use both ends when present.
    """
    d = data or {}
    start_raw = (d.get("start") or d.get("when") or d.get("raw") or "").strip()
    end_raw = (d.get("end") or "").strip()
    start = parse_ticket_date_token(start_raw)
    end = parse_ticket_date_token(end_raw) if end_raw else None
    if start is not None and end is None:
        end = start
    if start is not None and end is not None and end < start:
        # Swapped or messy range — still usable for OVER/ACTIVE
        start, end = end, start
    return start, end


# Calendar phase labels on date-ticket rows (look / examine)
TICKET_PHASE_ACTIVE = "ACTIVE"
TICKET_PHASE_OVER = "OVER"
TICKET_PHASE_NEXT = "NEXT"
TICKET_PHASE_LABELS = (
    TICKET_PHASE_ACTIVE,
    TICKET_PHASE_OVER,
    TICKET_PHASE_NEXT,
)


def ticket_calendar_phase(
    data: dict[str, Any] | None,
    *,
    today: date | None = None,
    next_starts: set[date] | frozenset[date] | None = None,
) -> str | None:
    """
    Calendar phase for a *date* ticket relative to *today*::

      OVER   — window ended (end < today), or point date in the past
      ACTIVE — today falls in [start, end] (point: start == today)
      NEXT   — start is the soonest future start among peers (*next_starts*)

    Returns None when unparseable or future-but-not-next.
    """
    today = today or date.today()
    start, end = ticket_date_bounds(data)
    if start is None or end is None:
        return None
    if end < today:
        return TICKET_PHASE_OVER
    if start <= today <= end:
        return TICKET_PHASE_ACTIVE
    # Future start
    if start > today and next_starts and start in next_starts:
        return TICKET_PHASE_NEXT
    return None


def next_upcoming_starts(
    data_list: list[dict[str, Any] | None],
    *,
    today: date | None = None,
) -> set[date]:
    """
    The earliest future start date(s) among date-ticket payloads.

    All tickets sharing that start are "NEXT" (ties kept together).
    """
    today = today or date.today()
    future: list[date] = []
    for data in data_list:
        start, end = ticket_date_bounds(data)
        if start is None or end is None:
            continue
        # Already over — skip
        if end < today:
            continue
        # Currently active — not "upcoming"
        if start <= today <= end:
            continue
        if start > today:
            future.append(start)
    if not future:
        return set()
    soonest = min(future)
    return {soonest}


def ticket_phase_markup(phase: str | None) -> str:
    """
    Colored lead tag for presence col1 (empty string if none).

    Date slips: ACTIVE / OVER / NEXT.
    Assignment slips: free staffer role (lead, oncall, …) in amber.
    """
    if not phase:
        return ""
    colors = {
        TICKET_PHASE_ACTIVE: "bold bright_green",
        TICKET_PHASE_OVER: "dim",
        TICKET_PHASE_NEXT: "bold bright_cyan",
    }
    style = colors.get(phase, "bold yellow")
    return f"[{style}]{phase}[/{style}]"


def parse_range_text(raw: str) -> dict[str, Any]:
    """
    Parse a human range string into start/end marks.

    ``Jan 20 - Feb 15 2026`` → start/end + raw.
    Single side (no separator) stores only raw (and start=raw).
    """
    s = (raw or "").strip()
    if not s:
        return {"raw": "", "start": "", "end": ""}
    parts = _RANGE_SPLIT.split(s, maxsplit=1)
    if len(parts) == 2:
        start, end = parts[0].strip(), parts[1].strip()
        return {"raw": s, "start": start, "end": end}
    return {"raw": s, "start": s, "end": ""}


def normalize_ticket_data(
    subtype: str,
    kind: str,
    description: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build tdf_data payload from flags + description."""
    out: dict[str, Any] = dict(data or {})
    sub = canonical_ticket_subtype(subtype) or (subtype or "").lower().strip()
    k_raw = (kind or "").strip()
    k = k_raw.lower()
    desc = (description or "").strip()

    if is_assignment_subtype(sub):
        # Person fields usually pre-filled by print path; -k is staff role
        if k_raw:
            out.setdefault("staff_kind", k_raw)
        if desc and "person_name" not in out:
            out.setdefault("raw", desc)
        out["subtype"] = "assignment"
        out["kind"] = k_raw  # free staffer type (preserve case)
        return out

    # Date/range slips parse -d into start/end; notes keep free text as title mostly
    if k == "range" or (sub == "date" and desc and "start" not in out):
        rng = parse_range_text(desc)
        out.setdefault("start", rng.get("start") or "")
        out.setdefault("end", rng.get("end") or "")
        out.setdefault("raw", rng.get("raw") or desc)
    elif desc and "raw" not in out:
        out["raw"] = desc
        if k == "due" or k == "point":
            out.setdefault("when", desc)
            out.setdefault("start", desc)

    out.setdefault("subtype", sub)
    if k:
        out["kind"] = k
    else:
        out.setdefault("kind", "")
    return out


def build_ticket_description(
    subtype: str, kind: str, data: dict[str, Any]
) -> str:
    """Readable slip body when the user did not pass -d."""
    sub = canonical_ticket_subtype(subtype) or (subtype or "ticket")
    if is_assignment_subtype(sub):
        person = (data.get("person_name") or data.get("raw") or "").strip()
        role = ticket_staff_kind(data, kind)
        if person and role:
            return f"assignment  ·  {role}  ·  {person}"
        if person:
            return f"assignment  ·  {person}"
        if role:
            return f"assignment  ·  {role}"
        return "assignment ticket"
    k = kind or "slip"
    start = (data.get("start") or "").strip()
    end = (data.get("end") or "").strip()
    raw = (data.get("raw") or data.get("when") or "").strip()
    if start and end:
        return f"{sub}/{k}  ·  {start} → {end}"
    if start:
        return f"{sub}/{k}  ·  {start}"
    if raw:
        return f"{sub}/{k}  ·  {raw}"
    return f"{sub}/{k} ticket"
