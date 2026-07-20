"""Temporary Data Fragments — printed tickets (slips), not full VEN primes."""

from __future__ import annotations

import re
from typing import Any

# Range separators in free text: "Jan 20 - Feb 15 2026"
_RANGE_SPLIT = re.compile(
    r"\s+[-–—]\s+|\s+to\s+|\s+through\s+|\s+thru\s+",
    re.IGNORECASE,
)

# Ticket subtypes (calendar / office)
TICKET_SUBTYPES = frozenset({"date", "label", "note", "tag"})
# Ticket kinds (due / state semantics)
TICKET_KINDS = frozenset({"range", "due", "state", "point", "open"})


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
    sub = (subtype or "").lower().strip()
    k = (kind or "").lower().strip()
    desc = (description or "").strip()

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
    out.setdefault("kind", k)
    return out


def build_ticket_description(
    subtype: str, kind: str, data: dict[str, Any]
) -> str:
    """Readable slip body when the user did not pass -d."""
    sub = subtype or "ticket"
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
