"""World operations over the VEN model."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .db import get_meta, set_meta
from .ids import (
    cute_name,
    digits_from_short_ref,
    format_instance_ref,
    format_instance_short_ref,
    format_ven_code,
    kind_code_prefix,
    names_match,
    new_id,
    new_tdf_code,
    normalize_formal_name,
    normalize_instance_title,
    parse_instance_ref_token,
    parse_resolve_query,
    parse_tdf_code,
    parse_ven_code,
    slugify,
)


# Lean roots — known systems of being (see IDEAS.md design lock).
# realm/timeline stay for layer chrome (not “adventure furniture” roots).
KINDS = (
    "person",
    "place",
    "bin",
    "thing",
    "folio",
    "symbol",
    "sense",
    "event",
    "ticket",  # TDF slips (print ticket) — movable, not prime-catalog furniture
    "realm",
    "timeline",
)

# Contained in a person → examine/who "Inner life" (not generic Contains)
INNER_LIFE_KINDS = frozenset({"sense"})

# Furniture that stores (placement buckets on look). ``container`` = legacy DB rows.
BIN_KINDS = frozenset({"bin", "container"})

# Legacy names accepted at create/parse; folded into lean roots + optional subtype.
# Also used so older docs/tests can still say feeling/book/object briefly.
KIND_ALIASES: dict[str, str] = {
    "object": "thing",
    "material": "thing",
    "book": "folio",
    "concept": "symbol",
    "feeling": "sense",
    "goal": "sense",
    "desire": "sense",
    "purpose": "sense",
    # event is a root again (was briefly folded to sense/event)
    "archetype": "person",  # person/archetype — persons of symbols
    "other": "thing",
    # container was the old store-root; box/crate are casual synonyms
    "container": "bin",
    "box": "bin",
    "crate": "bin",
}

# Author subtypes welcome on all adventure roots (not only a “feeling group”)
SUBTYPE_KINDS = frozenset(
    {
        "person",
        "place",
        "bin",
        "thing",
        "folio",
        "symbol",
        "sense",
        "event",
        "ticket",
    }
)

# Instance state keys for Temporary Data Fragments (printed tickets)
TDF_STATE_KEY = "tdf"
TDF_CODE_KEY = "tdf_code"
TDF_TYPE_KEY = "tdf_type"  # ticket
TDF_SUBTYPE_KEY = "tdf_subtype"  # date, …
TDF_KIND_KEY = "tdf_kind"  # range, due, state, …
TDF_DATA_KEY = "tdf_data"  # payload dict (range start/end, …)

# Back-compat name used in a few create/help strings
FEELING_GROUP_KINDS = frozenset({"sense"})

LINK_TYPES = ("spatial", "dimensional", "temporal", "narrative", "conditional")
# Compact path-list prefixes (fixed width 2 for column scan)
LINK_TYPE_CODES: dict[str, str] = {
    "spatial": "sp",
    "dimensional": "di",
    "temporal": "te",
    "narrative": "na",
    "conditional": "co",
}

# Instance state key: object portal → place instance id (run travel; not room exits)
PORTAL_STATE_KEY = "portal_to"
# Portal lock: bool — when true, open/run/enter fail until unlock
PORTAL_LOCKED_KEY = "portal_locked"
# Portal key: specific key *instance* id (prime Key + many named spawns)
PORTAL_KEY_INSTANCE_KEY = "portal_key_instance_id"
# Legacy: key by prime VEN (any spawn of that prime). Prefer instance bind.
PORTAL_KEY_VEN_KEY = "portal_key_ven_id"
# Flavor line shown when open/run fails while locked (set via lock -d)
PORTAL_LOCK_DENY_KEY = "portal_lock_deny"
# Player state: stack of run sessions for logout (return place, not a room exit)
PORTAL_STACK_KEY = "portal_stack"

CONTAINMENT_SLOTS = (
    "interior",
    "inventory",
    "worn",
    "sense",
    "archetype",
    # legacy inner slots (still accepted)
    "feeling",
    "goal",
    "desire",
    "purpose",
    "memory",
    "motif",
    "event",
)


def is_inner_life_kind(kind: str, subtype: str | None = None) -> bool:
    """Sense (and person/archetype) may live in a person's Inner life."""
    k = (kind or "").lower()
    sub = (subtype or "").strip().lower()
    if k in INNER_LIFE_KINDS:
        return True
    if k == "person" and sub == "archetype":
        return True
    # legacy
    if k in ("feeling", "goal", "desire", "purpose", "archetype"):
        return True
    return False


def default_inner_slot(kind: str, subtype: str | None = None) -> str:
    """Default containment slot when putting an inner-life kind into a person."""
    k = (kind or "").lower()
    sub = (subtype or "").strip().lower()
    if k == "person" and sub == "archetype":
        return "archetype"
    if k in INNER_LIFE_KINDS:
        return "sense"
    # legacy slots still accepted by put
    if k in ("feeling", "goal", "desire", "purpose", "archetype"):
        return k if k != "archetype" else "archetype"
    return "interior"


def parse_kind_spec(raw: str) -> tuple[str, str | None]:
    """
    Parse ``kind`` or ``kind/subtype`` (also ``kind:subtype``).

    Returns (kind, subtype|None) after alias fold. Does not validate against KINDS.
    """
    s = (raw or "").strip()
    if not s:
        return "", None
    kind: str
    sub: str | None
    for sep in ("/", ":"):
        if sep in s:
            left, _, right = s.partition(sep)
            kind = left.strip().lower()
            sub = right.strip().lower() or None
            return normalize_kind(kind, sub)
    return normalize_kind(s.lower(), None)


def normalize_kind(
    kind: str, subtype: str | None = None
) -> tuple[str, str | None]:
    """
    Fold legacy kind names into lean roots; may invent a default subtype.

    Examples:
      book → folio/book
      feeling/longing → sense/longing
      feeling → sense/feeling
      archetype → person/archetype
      object → thing
      material → thing/material
      container / box / crate → bin
      event stays event (subtypes free: event/meeting, event/beat, …)
    """
    k = (kind or "").strip().lower()
    sub = (subtype or "").strip().lower() or None
    if k in KIND_ALIASES:
        new_k = KIND_ALIASES[k]
        if sub is None:
            if k == "archetype":
                sub = "archetype"
            elif k == "material":
                sub = "material"
            elif k == "book":
                sub = "book"
            elif k in ("feeling", "goal", "desire", "purpose"):
                sub = k
            elif k == "concept":
                sub = None
            elif k == "object":
                sub = None
            # container/box/crate → bin with no forced subtype
        return new_k, sub
    return k, sub


def format_kind_label(kind: str, subtype: str | None = None) -> str:
    """Display label e.g. feeling/longing or goal."""
    k = (kind or "").strip()
    if subtype:
        return f"{k}/{subtype}"
    return k


@dataclass
class VenView:
    id: str
    slug: str
    name: str
    kind: str
    description: str
    is_prime: bool
    tags: list[str]
    subtype: str | None = None
    meta: dict[str, Any] | None = None
    parent_ven_id: str | None = None
    code: str | None = None  # compact RLM-001 / OBJ-014


@dataclass
class VenPartView:
    """One composition edge: whole prime made of part prime with a role."""

    id: str
    whole_ven_id: str
    part_ven_id: str
    role: str
    ordinal: int
    notes: str
    part_name: str = ""
    part_slug: str = ""
    part_kind: str = ""


@dataclass
class CompositionNode:
    """One edge in a composition tree (part of a whole), with optional nested parts."""

    part: VenPartView
    children: list["CompositionNode"]
    is_cycle: bool = False


# Direct parts only (default list / wiki)
COMPOSITION_DEPTH_DEFAULT = 1
# Nested graph under parts (wiki X deep / compose X deep)
COMPOSITION_DEPTH_DEEP = 4


@dataclass
class InstanceView:
    id: str
    ven_id: str
    ven_name: str
    ven_kind: str
    ven_slug: str
    name: str
    description: str
    realm_instance_id: str | None
    timeline_instance_id: str | None
    state: dict[str, Any]
    ven_subtype: str | None = None
    ven_code: str | None = None


class World:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        from .undo import UndoStack

        self.undo_stack = UndoStack()
        # In-progress talk session (DialogSession | None); not persisted mid-chat
        self.active_dialog: Any = None

    # ── VEN / instance creation ──────────────────────────────────────────

    def create_ven(
        self,
        name: str,
        kind: str,
        description: str = "",
        slug: str | None = None,
        tags: list[str] | None = None,
        is_prime: bool = True,
        elevated_from_instance_id: str | None = None,
        meta: dict[str, Any] | None = None,
        parent_ven_id: str | None = None,
        code: str | None = None,
    ) -> str:
        # Fold legacy kinds (feeling→sense, book→folio, …) at the waist
        st0 = None
        if meta and meta.get("subtype") is not None:
            st0 = str(meta.get("subtype") or "") or None
        kind, st0 = normalize_kind(kind, st0)
        if st0:
            meta = dict(meta or {})
            meta["subtype"] = st0
        if kind not in KINDS:
            raise ValueError(f"Unknown kind {kind!r}; expected one of {KINDS}")
        if parent_ven_id is not None:
            if self.get_ven(parent_ven_id) is None:
                raise ValueError(f"No parent VEN {parent_ven_id}")
        # Formal display name preserves case and ' " - ; slug is cute match key
        formal = normalize_formal_name(name)
        base = slugify(slug or name)
        final_slug = base
        n = 2
        while self.conn.execute("SELECT 1 FROM vens WHERE slug = ?", (final_slug,)).fetchone():
            final_slug = f"{base}-{n}"
            n += 1
        if code:
            final_code = parse_ven_code(code) or code.strip().upper()
            if self.get_ven_by_code(final_code) is not None:
                raise ValueError(f"VEN code {final_code} already in use")
        else:
            final_code = self.allocate_ven_code(kind)
        ven_id = new_id("ven")
        self.conn.execute(
            """
            INSERT INTO vens(id, slug, code, name, kind, description, is_prime,
                             elevated_from_instance_id, parent_ven_id,
                             tags_json, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ven_id,
                final_slug,
                final_code,
                formal,
                kind,
                description,
                1 if is_prime else 0,
                elevated_from_instance_id,
                parent_ven_id,
                json.dumps(tags or []),
                json.dumps(meta or {}),
            ),
        )
        self.conn.commit()
        return ven_id

    def allocate_ven_code(self, kind: str) -> str:
        """Next compact code for this kind: RLM-001, OBJ-014, …"""
        prefix = kind_code_prefix(kind)
        rows = self.conn.execute(
            "SELECT code FROM vens WHERE code IS NOT NULL AND code != ''"
        ).fetchall()
        max_n = 0
        for r in rows:
            parsed = parse_ven_code(r["code"])
            if not parsed:
                continue
            pref, _, num = parsed.partition("-")
            if pref != prefix:
                continue
            try:
                max_n = max(max_n, int(num))
            except ValueError:
                continue
        return format_ven_code(prefix, max_n + 1)

    def get_ven_by_code(self, code: str) -> VenView | None:
        canon = parse_ven_code(code)
        if not canon:
            return None
        row = self.conn.execute(
            "SELECT id FROM vens WHERE upper(code) = ?",
            (canon,),
        ).fetchone()
        if row:
            return self.get_ven(row["id"])
        return None

    def instantiate(
        self,
        ven_id: str,
        *,
        name_override: str | None = None,
        description_override: str | None = None,
        realm_instance_id: str | None = None,
        timeline_instance_id: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> str:
        if not self.conn.execute("SELECT 1 FROM vens WHERE id = ?", (ven_id,)).fetchone():
            raise ValueError(f"No VEN {ven_id}")
        inst_id = new_id("inst")
        # Instance titles keep CAPS / separators; VEN primes still use cute_name
        override = (
            normalize_instance_title(name_override) if name_override else None
        )
        st = dict(state or {})
        # Never allow two instances of the same prime to share short_ref digits
        wanted = digits_from_short_ref(str(st.get("short_ref") or ""))
        taken = self._short_ref_digits_taken(ven_id)
        if wanted and wanted not in taken:
            st["short_ref"] = wanted
        else:
            st["short_ref"] = self._next_short_ref(ven_id)
        self.conn.execute(
            """
            INSERT INTO instances(
                id, ven_id, name_override, description_override,
                realm_instance_id, timeline_instance_id, state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inst_id,
                ven_id,
                override,
                description_override,
                realm_instance_id,
                timeline_instance_id,
                json.dumps(st),
            ),
        )
        self.conn.commit()
        return inst_id

    # ── Temporary Data Fragments (printed tickets) ───────────────────────

    def ensure_ticket_prime(self) -> str:
        """
        Shared Ticket prime for all TDF slips (one prime, many instances).

        Slips are not catalogued as separate VEN primes — only as movable
        instances with TDF-… codes in state_json.
        """
        existing = self.find_ven("Ticket")
        if existing is not None and (existing.kind or "").lower() == "ticket":
            return existing.id
        # Prefer code-stable prime named Ticket
        for v in self.list_vens():
            if (v.kind or "").lower() == "ticket" and names_match("Ticket", v.name):
                return v.id
        return self.create_ven(
            "Ticket",
            "ticket",
            description=(
                "Temporary Data Fragment template — slips of paper printed into "
                "the office (dates, dues, labels). Not a full VEN catalog entry "
                "per slip; each print is a TDF instance."
            ),
            tags=["tdf", "ticket", "office"],
            meta={"subtype": "template"},
        )

    def tdf_codes_taken(self) -> set[str]:
        """All TDF codes currently stored on instances."""
        taken: set[str] = set()
        rows = self.conn.execute("SELECT state_json FROM instances").fetchall()
        for r in rows:
            st = json.loads(r["state_json"] or "{}")
            code = parse_tdf_code(str(st.get(TDF_CODE_KEY) or ""))
            if code:
                taken.add(code)
        return taken

    def mint_tdf_code(self) -> str:
        """Unique TDF-######## for a new slip."""
        taken = self.tdf_codes_taken()
        for _ in range(64):
            code = new_tdf_code()
            if code not in taken:
                return code
        # Extremely unlikely collision storm
        return new_tdf_code()

    def is_tdf(self, instance_id: str) -> bool:
        st = self.instance_state(instance_id)
        return bool(st.get(TDF_STATE_KEY)) or bool(
            parse_tdf_code(str(st.get(TDF_CODE_KEY) or ""))
        )

    def tdf_payload(self, instance_id: str) -> dict[str, Any] | None:
        """Return TDF fields from instance state, or None if not a TDF."""
        st = self.instance_state(instance_id)
        if not st.get(TDF_STATE_KEY) and not st.get(TDF_CODE_KEY):
            return None
        return {
            "code": st.get(TDF_CODE_KEY),
            "type": st.get(TDF_TYPE_KEY) or "ticket",
            "subtype": st.get(TDF_SUBTYPE_KEY) or "",
            "kind": st.get(TDF_KIND_KEY) or "",
            "data": dict(st.get(TDF_DATA_KEY) or {}),
        }

    def find_instance_by_tdf_code(self, raw: str) -> InstanceView | None:
        code = parse_tdf_code(raw)
        if not code:
            return None
        rows = self.conn.execute("SELECT id, state_json FROM instances").fetchall()
        for r in rows:
            st = json.loads(r["state_json"] or "{}")
            if parse_tdf_code(str(st.get(TDF_CODE_KEY) or "")) == code:
                return self.get_instance(r["id"])
        return None

    def print_ticket(
        self,
        *,
        name: str,
        subtype: str,
        kind: str,
        description: str = "",
        data: dict[str, Any] | None = None,
        into_instance_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Print a ticket TDF into *into_instance_id* (default: current place).

        Returns (instance_id, tdf_code).
        """
        from .tdf import build_ticket_description, normalize_ticket_data

        loc = self.player_location()
        dest = into_instance_id
        if not dest:
            if not loc:
                raise ValueError("Nowhere to print — dig or go somewhere first.")
            dest = loc.id

        subtype_n = (subtype or "").strip().lower() or "date"
        # Empty kind is allowed (notes); do not force "range" on every slip
        kind_n = (kind or "").strip().lower()
        title = normalize_instance_title(name)
        payload = normalize_ticket_data(subtype_n, kind_n, description, data)
        desc = (description or "").strip() or build_ticket_description(
            subtype_n, kind_n, payload
        )
        code = self.mint_tdf_code()
        prime = self.ensure_ticket_prime()
        # Align realm/timeline with destination when possible
        dest_inst = self.get_instance(dest)
        realm_id = dest_inst.realm_instance_id if dest_inst else None
        timeline_id = dest_inst.timeline_instance_id if dest_inst else None
        if loc and not realm_id:
            realm_id = loc.realm_instance_id
            timeline_id = loc.timeline_instance_id

        st = {
            TDF_STATE_KEY: True,
            TDF_CODE_KEY: code,
            TDF_TYPE_KEY: "ticket",
            TDF_SUBTYPE_KEY: subtype_n,
            TDF_KIND_KEY: kind_n,
            TDF_DATA_KEY: payload,
        }
        inst_id = self.instantiate(
            prime,
            name_override=title,
            description_override=desc,
            realm_instance_id=realm_id,
            timeline_instance_id=timeline_id,
            state=st,
        )
        self.put_in(inst_id, dest, slot="interior")
        return inst_id, code

    def _short_ref_digits_taken(self, ven_id: str) -> set[str]:
        """All short_ref digit parts already used by instances of this prime."""
        taken: set[str] = set()
        rows = self.conn.execute(
            "SELECT state_json FROM instances WHERE ven_id = ?",
            (ven_id,),
        ).fetchall()
        for r in rows:
            st = json.loads(r["state_json"] or "{}")
            dig = digits_from_short_ref(str(st.get("short_ref") or ""))
            if dig:
                taken.add(dig)
        return taken

    def _next_short_ref(self, ven_id: str) -> str:
        """Next sequential digit ref for this prime (stored as 0001, 0002, …)."""
        taken = self._short_ref_digits_taken(ven_id)
        max_n = 0
        for dig in taken:
            try:
                max_n = max(max_n, int(dig))
            except ValueError:
                continue
        return format_instance_ref(max_n + 1)

    def find_instance_by_import_key(
        self,
        *,
        home_instance_ref: str,
        origin_world: str,
    ) -> InstanceView | None:
        """Find an instance previously imported from the same origin pack key."""
        href = (home_instance_ref or "").strip()
        oworld = (origin_world or "").strip()
        if not href:
            return None
        rows = self.conn.execute("SELECT id, state_json FROM instances").fetchall()
        for r in rows:
            st = json.loads(r["state_json"] or "{}")
            ie = st.get("ie") if isinstance(st.get("ie"), dict) else {}
            if not ie:
                continue
            if str(ie.get("home_instance_ref") or "").strip().casefold() != href.casefold():
                continue
            if oworld and str(ie.get("origin_world") or "").strip().casefold() != oworld.casefold():
                continue
            inst = self.get_instance(r["id"])
            if inst:
                return inst
        return None

    def instance_state(self, instance_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT state_json FROM instances WHERE id = ?",
            (instance_id,),
        ).fetchone()
        if not row:
            return {}
        return json.loads(row["state_json"] or "{}")

    def set_instance_state(self, instance_id: str, state: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE instances SET state_json = ? WHERE id = ?",
            (json.dumps(state), instance_id),
        )
        self.conn.commit()

    def get_portal_to(self, instance_id: str) -> str | None:
        """Place instance id this object runs into, if bound."""
        raw = self.instance_state(instance_id).get(PORTAL_STATE_KEY)
        if not raw:
            return None
        dest_id = str(raw).strip()
        return dest_id or None

    def set_portal_to(self, instance_id: str, place_instance_id: str | None) -> None:
        """
        Bind or clear object → place portal (run travel; not listed in exits).

        Stored on the **app instance** ``state_json`` (not on containment).
        take / drop / put / install never clear this — only portal clear (or
        explicit set to None) does. Install-in-device is presence for run only.
        Clearing the portal also clears lock + key bind.
        """
        st = self.instance_state(instance_id)
        if place_instance_id is None:
            st.pop(PORTAL_STATE_KEY, None)
            st.pop(PORTAL_LOCKED_KEY, None)
            st.pop(PORTAL_KEY_INSTANCE_KEY, None)
            st.pop(PORTAL_KEY_VEN_KEY, None)
            st.pop(PORTAL_LOCK_DENY_KEY, None)
        else:
            dest = self.get_instance(place_instance_id)
            if dest is None or dest.ven_kind != "place":
                raise ValueError("Portal destination must be a place instance")
            st[PORTAL_STATE_KEY] = place_instance_id
        self.set_instance_state(instance_id, st)

    def is_portal_locked(self, instance_id: str) -> bool:
        """True when portal token requires unlock before open/run/enter."""
        raw = self.instance_state(instance_id).get(PORTAL_LOCKED_KEY)
        if raw is True or raw == 1:
            return True
        if isinstance(raw, str) and raw.strip().lower() in ("1", "true", "yes", "locked"):
            return True
        return False

    def set_portal_locked(self, instance_id: str, locked: bool) -> None:
        st = self.instance_state(instance_id)
        if locked:
            st[PORTAL_LOCKED_KEY] = True
        else:
            st.pop(PORTAL_LOCKED_KEY, None)
        self.set_instance_state(instance_id, st)

    def get_portal_key_instance_id(self, instance_id: str) -> str | None:
        """Specific key instance that unlocks this portal (preferred bind)."""
        raw = self.instance_state(instance_id).get(PORTAL_KEY_INSTANCE_KEY)
        if not raw:
            return None
        kid = str(raw).strip()
        return kid or None

    def set_portal_key_instance_id(
        self, instance_id: str, key_instance_id: str | None
    ) -> None:
        """
        Bind or clear the exact key instance for this portal.

        Authoring model: one prime Key, many named spawns (Cellar Key, Suite Key).
        ``lock door with cellar-key`` binds that copy — not every Key spawn.
        """
        st = self.instance_state(instance_id)
        if key_instance_id is None:
            st.pop(PORTAL_KEY_INSTANCE_KEY, None)
        else:
            st[PORTAL_KEY_INSTANCE_KEY] = key_instance_id
            # Instance bind supersedes legacy prime-wide bind
            st.pop(PORTAL_KEY_VEN_KEY, None)
        self.set_instance_state(instance_id, st)

    def get_portal_key_ven_id(self, instance_id: str) -> str | None:
        """Legacy: VEN id of key prime (any spawn). Prefer instance bind."""
        raw = self.instance_state(instance_id).get(PORTAL_KEY_VEN_KEY)
        if not raw:
            return None
        vid = str(raw).strip()
        return vid or None

    def set_portal_key_ven_id(
        self, instance_id: str, key_ven_id: str | None
    ) -> None:
        """Legacy prime-wide key bind. Prefer :meth:`set_portal_key_instance_id`."""
        st = self.instance_state(instance_id)
        if key_ven_id is None:
            st.pop(PORTAL_KEY_VEN_KEY, None)
        else:
            st[PORTAL_KEY_VEN_KEY] = key_ven_id
        self.set_instance_state(instance_id, st)

    def portal_requires_key(self, portal_id: str) -> bool:
        """True when a specific key (instance or legacy ven) is bound."""
        return bool(
            self.get_portal_key_instance_id(portal_id)
            or self.get_portal_key_ven_id(portal_id)
        )

    def portal_key_matches(self, portal_id: str, key: InstanceView) -> bool:
        """True if *key* is the bound instance (or legacy same-VEN key)."""
        need_inst = self.get_portal_key_instance_id(portal_id)
        if need_inst:
            return key.id == need_inst
        need_ven = self.get_portal_key_ven_id(portal_id)
        if need_ven:
            return bool(key.ven_id and key.ven_id == need_ven)
        return True  # keyless lock

    def portal_key_label(self, portal_id: str) -> str:
        """Player-facing name of the required key, or 'the right key'."""
        from .ids import display_name as _dn

        need_inst = self.get_portal_key_instance_id(portal_id)
        if need_inst:
            k = self.get_instance(need_inst)
            if k is not None:
                return _dn(k.name)
            return "the right key"
        need_ven = self.get_portal_key_ven_id(portal_id)
        if need_ven:
            v = self.get_ven(need_ven)
            if v is not None:
                return _dn(v.name)
        return "the right key"

    def get_portal_lock_deny(self, instance_id: str) -> str | None:
        """Author flavor shown when open/run hits a locked portal (``lock -d``)."""
        raw = self.instance_state(instance_id).get(PORTAL_LOCK_DENY_KEY)
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None

    def set_portal_lock_deny(
        self, instance_id: str, message: str | None
    ) -> None:
        """Set or clear the locked-door refuse line."""
        st = self.instance_state(instance_id)
        if message is None or not str(message).strip():
            st.pop(PORTAL_LOCK_DENY_KEY, None)
        else:
            st[PORTAL_LOCK_DENY_KEY] = str(message).strip()
        self.set_instance_state(instance_id, st)

    def install_container_of(self, instance_id: str) -> InstanceView | None:
        """
        Parent container that counts as an install site for ``run``.

        Floor (place) and loose inventory (player) are not installs.
        Any other container object/person/etc. is fine (terminal, bag, …).
        Install does **not** own the portal binding (see :meth:`set_portal_to`).
        """
        cont = self.container_of(instance_id)
        if not cont:
            return None
        holder = self.get_instance(cont[0])
        if holder is None:
            return None
        if holder.ven_kind == "place":
            return None
        pid = self.player_id()
        if pid and holder.id == pid:
            return None
        return holder

    def is_installed(self, instance_id: str) -> bool:
        return self.install_container_of(instance_id) is not None

    def portal_stack(self) -> list[dict[str, Any]]:
        """Active run sessions on the player (most recent last)."""
        pid = self.player_id()
        if not pid:
            return []
        raw = self.instance_state(pid).get(PORTAL_STACK_KEY) or []
        if not isinstance(raw, list):
            return []
        return [x for x in raw if isinstance(x, dict)]

    def push_portal_session(
        self,
        *,
        return_place_id: str,
        app_id: str | None = None,
        app_name: str = "",
        device_id: str | None = None,
        device_name: str = "",
        dest_place_id: str | None = None,
        dest_name: str = "",
    ) -> None:
        """Record that the player ran into a world; logout pops this frame."""
        pid = self.player_id()
        if not pid:
            raise ValueError("No player set")
        st = self.instance_state(pid)
        stack = list(st.get(PORTAL_STACK_KEY) or [])
        if not isinstance(stack, list):
            stack = []
        stack.append(
            {
                "return_place_id": return_place_id,
                "app_id": app_id,
                "app_name": app_name,
                "device_id": device_id,
                "device_name": device_name,
                "dest_place_id": dest_place_id,
                "dest_name": dest_name,
            }
        )
        st[PORTAL_STACK_KEY] = stack
        self.set_instance_state(pid, st)

    def pop_portal_session(self) -> dict[str, Any] | None:
        """Pop the most recent run session, or None if not in one."""
        pid = self.player_id()
        if not pid:
            return None
        st = self.instance_state(pid)
        stack = list(st.get(PORTAL_STACK_KEY) or [])
        if not isinstance(stack, list) or not stack:
            return None
        frame = stack.pop()
        if stack:
            st[PORTAL_STACK_KEY] = stack
        else:
            st.pop(PORTAL_STACK_KEY, None)
        self.set_instance_state(pid, st)
        return frame if isinstance(frame, dict) else None

    def peek_portal_session(self) -> dict[str, Any] | None:
        stack = self.portal_stack()
        return stack[-1] if stack else None

    def short_ref_of(self, instance_id: str) -> str:
        """
        Player-facing short ref: prefer compact ``OBJ-014-0001`` (VEN code + seq).

        Digits are stored per prime; code/slug is joined at read time.
        """
        st = self.instance_state(instance_id)
        raw = str(st.get("short_ref") or "").strip()
        dig = digits_from_short_ref(raw)
        inst = self.get_instance(instance_id)
        if inst is None:
            return "----"
        if dig is None:
            dig = self._next_short_ref(inst.ven_id)
            st["short_ref"] = dig
            self.set_instance_state(instance_id, st)
        elif raw != dig:
            # Normalize legacy composite storage back to digits only
            st["short_ref"] = dig
            self.set_instance_state(instance_id, st)
        slug = inst.ven_slug or inst.ven_name or "ITEM"
        return format_instance_short_ref(
            slug, dig, ven_code=inst.ven_code
        )

    def short_ref_matches(self, instance_id: str, query_ref: str) -> bool:
        """True if *query_ref* (digits, code, or legacy slug composite) names this instance.

        Soft typing: spaces/underscores act like dashes
        (``bin 003 0043`` matches ``BIN-003-0043``).
        """
        from .ids import normalize_ref_separators

        q = (query_ref or "").strip().lstrip("#")
        if not q:
            return False
        full = self.short_ref_of(instance_id)
        if q.casefold() == full.casefold():
            return True
        # Soft separators → canonical compare
        q_soft = normalize_ref_separators(q)
        full_soft = normalize_ref_separators(full)
        if q_soft and q_soft.casefold() == full_soft.casefold():
            return True
        inst = self.get_instance(instance_id)
        dig = digits_from_short_ref(full)
        # Legacy cute-slug composite (FIELD-NOTES-0001) still resolves
        if inst is not None and dig:
            legacy = format_instance_short_ref(
                inst.ven_slug or inst.ven_name or "ITEM",
                dig,
                ven_code=None,
            )
            if q.casefold() == legacy.casefold():
                return True
            if normalize_ref_separators(legacy).casefold() == q_soft.casefold():
                return True
        parsed = parse_instance_ref_token(q)
        if parsed:
            if parsed.casefold() == full.casefold():
                return True
            if parsed.isdigit() and dig == parsed:
                return True
        if q.isdigit() and dig == format_instance_ref(int(q)):
            return True
        return False

    def get_name_override(self, instance_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT name_override FROM instances WHERE id = ?",
            (instance_id,),
        ).fetchone()
        if row is None:
            return None
        return row["name_override"]

    def set_name_override(self, instance_id: str, name: str | None) -> None:
        override = normalize_instance_title(name) if name else None
        self.conn.execute(
            "UPDATE instances SET name_override = ? WHERE id = ?",
            (override, instance_id),
        )
        self.conn.commit()

    def set_ven_name(
        self,
        ven_id: str,
        name: str,
        *,
        reslug: bool = False,
    ) -> VenView:
        """
        Rename a prime's formal display name.

        Slug stays put by default (codes/refs stable). Pass reslug=True to
        recompute a free cute slug from the new name.
        """
        ven = self.get_ven(ven_id)
        if ven is None:
            raise ValueError(f"No VEN {ven_id}")
        formal = normalize_formal_name(name)
        if reslug:
            base = slugify(formal)
            final_slug = base
            n = 2
            while True:
                row = self.conn.execute(
                    "SELECT id FROM vens WHERE slug = ? AND id != ?",
                    (final_slug, ven_id),
                ).fetchone()
                if row is None:
                    break
                final_slug = f"{base}-{n}"
                n += 1
            self.conn.execute(
                "UPDATE vens SET name = ?, slug = ? WHERE id = ?",
                (formal, final_slug, ven_id),
            )
        else:
            self.conn.execute(
                "UPDATE vens SET name = ? WHERE id = ?",
                (formal, ven_id),
            )
        self.conn.commit()
        updated = self.get_ven(ven_id)
        assert updated is not None
        return updated

    def list_instances_of_ven(self, ven_id: str) -> list[InstanceView]:
        rows = self.conn.execute(
            "SELECT id FROM instances WHERE ven_id = ? ORDER BY created_at",
            (ven_id,),
        ).fetchall()
        return [self.get_instance(r["id"]) for r in rows if self.get_instance(r["id"])]  # type: ignore[misc]

    def where_label(self, instance_id: str) -> str:
        """here / inv / in <container> / nowhere for player-facing lists."""
        pid = self.player_id()
        loc = self.player_location()
        cont = self.container_of(instance_id)
        if cont is None:
            return "nowhere"
        cid, slot = cont
        if pid and cid == pid and slot == "inventory":
            return "inv"
        if loc and cid == loc.id:
            return "here"
        holder = self.get_instance(cid)
        hname = holder.name if holder else cid
        return f"in {hname}"

    def elevate_instance_to_prime(self, instance_id: str, name: str | None = None) -> str:
        """
        Promote a lived instance into a new Prime VEN and rebind the instance to it.

        The new prime's parent is the origin prime. Provenance fields
        elevated_from_instance_id / became_prime_ven_id are also set.
        Short-ref digits are reassigned under the new prime (usually 0001).
        """
        inst = self.get_instance(instance_id)
        if inst is None:
            raise ValueError(f"No instance {instance_id}")
        origin_ven_id = inst.ven_id
        # Prefer the lived instance title; slug uniqueness uses -2, -3 (not -PRIME)
        prime_name = (name or inst.name or "Elevated").strip() or "Elevated"
        ven_id = self.create_ven(
            name=prime_name,
            kind=inst.ven_kind,
            description=inst.description,
            elevated_from_instance_id=instance_id,
            parent_ven_id=origin_ven_id,
            tags=["elevated"],
        )
        self.conn.execute(
            """
            UPDATE instances
            SET became_prime_ven_id = ?, ven_id = ?
            WHERE id = ?
            """,
            (ven_id, ven_id, instance_id),
        )
        # Re-number short_ref under the elevated prime (drop stale origin digits)
        st = self.instance_state(instance_id)
        st.pop("short_ref", None)
        self.set_instance_state(instance_id, st)
        st["short_ref"] = self._next_short_ref(ven_id)
        self.set_instance_state(instance_id, st)
        self.conn.commit()
        return ven_id

    # ── Specialization lineage ───────────────────────────────────────────

    def set_parent_ven(self, ven_id: str, parent_ven_id: str | None) -> None:
        """Set specialization parent; None clears to root. Rejects cycles."""
        if self.get_ven(ven_id) is None:
            raise ValueError(f"No VEN {ven_id}")
        if parent_ven_id is not None:
            if parent_ven_id == ven_id:
                raise ValueError("A VEN cannot be its own parent")
            if self.get_ven(parent_ven_id) is None:
                raise ValueError(f"No parent VEN {parent_ven_id}")
            # Walk ancestors of proposed parent — must not hit ven_id
            walk: str | None = parent_ven_id
            seen: set[str] = set()
            while walk:
                if walk == ven_id:
                    raise ValueError("Would create a cycle in VEN lineage")
                if walk in seen:
                    break
                seen.add(walk)
                p = self.get_ven(walk)
                walk = p.parent_ven_id if p else None
        self.conn.execute(
            "UPDATE vens SET parent_ven_id = ? WHERE id = ?",
            (parent_ven_id, ven_id),
        )
        self.conn.commit()

    def parent_of(self, ven_id: str) -> VenView | None:
        ven = self.get_ven(ven_id)
        if ven is None or not ven.parent_ven_id:
            return None
        return self.get_ven(ven.parent_ven_id)

    def children_of(self, ven_id: str) -> list[VenView]:
        rows = self.conn.execute(
            """
            SELECT id FROM vens
            WHERE parent_ven_id = ?
            ORDER BY name COLLATE NOCASE
            """,
            (ven_id,),
        ).fetchall()
        out: list[VenView] = []
        for r in rows:
            v = self.get_ven(r["id"])
            if v:
                out.append(v)
        return out

    def ancestors(self, ven_id: str) -> list[VenView]:
        """Root-first chain of parents (does not include self)."""
        chain: list[VenView] = []
        walk = self.parent_of(ven_id)
        seen: set[str] = set()
        while walk is not None and walk.id not in seen:
            chain.append(walk)
            seen.add(walk.id)
            walk = self.parent_of(walk.id)
        chain.reverse()
        return chain

    def lineage_path(self, ven_id: str) -> list[VenView]:
        """Root → … → self."""
        ven = self.get_ven(ven_id)
        if ven is None:
            return []
        return self.ancestors(ven_id) + [ven]

    def root_vens(self) -> list[VenView]:
        """Primes with no parent (specialization roots)."""
        rows = self.conn.execute(
            """
            SELECT id FROM vens
            WHERE parent_ven_id IS NULL
            ORDER BY kind, name COLLATE NOCASE
            """
        ).fetchall()
        out: list[VenView] = []
        for r in rows:
            v = self.get_ven(r["id"])
            if v:
                out.append(v)
        return out

    # ── Composition (ven_parts) ──────────────────────────────────────────

    def add_ven_part(
        self,
        whole_ven_id: str,
        part_ven_id: str,
        role: str = "part",
        ordinal: int | None = None,
        notes: str = "",
    ) -> str:
        if whole_ven_id == part_ven_id:
            raise ValueError("A VEN cannot be a part of itself")
        if self.get_ven(whole_ven_id) is None:
            raise ValueError(f"No whole VEN {whole_ven_id}")
        if self.get_ven(part_ven_id) is None:
            raise ValueError(f"No part VEN {part_ven_id}")
        role_s = (role or "part").strip().lower() or "part"
        if ordinal is None:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(ordinal), -1) AS m FROM ven_parts WHERE whole_ven_id = ?",
                (whole_ven_id,),
            ).fetchone()
            ordinal = int(row["m"]) + 1 if row else 0
        pid = new_id("vpart")
        self.conn.execute(
            """
            INSERT INTO ven_parts(id, whole_ven_id, part_ven_id, role, ordinal, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pid, whole_ven_id, part_ven_id, role_s, ordinal, notes or ""),
        )
        self.conn.commit()
        return pid

    def remove_ven_part(
        self,
        whole_ven_id: str,
        part_ven_id: str,
        role: str | None = None,
    ) -> int:
        """Remove composition edge(s). Returns number of rows deleted."""
        if role:
            cur = self.conn.execute(
                """
                DELETE FROM ven_parts
                WHERE whole_ven_id = ? AND part_ven_id = ? AND role = ?
                """,
                (whole_ven_id, part_ven_id, role.strip().lower()),
            )
        else:
            cur = self.conn.execute(
                """
                DELETE FROM ven_parts
                WHERE whole_ven_id = ? AND part_ven_id = ?
                """,
                (whole_ven_id, part_ven_id),
            )
        self.conn.commit()
        return cur.rowcount

    def list_ven_parts(self, whole_ven_id: str) -> list[VenPartView]:
        rows = self.conn.execute(
            """
            SELECT p.*, v.name AS part_name, v.slug AS part_slug, v.kind AS part_kind
            FROM ven_parts p
            JOIN vens v ON v.id = p.part_ven_id
            WHERE p.whole_ven_id = ?
            ORDER BY p.ordinal, v.name COLLATE NOCASE
            """,
            (whole_ven_id,),
        ).fetchall()
        return [
            VenPartView(
                id=r["id"],
                whole_ven_id=r["whole_ven_id"],
                part_ven_id=r["part_ven_id"],
                role=r["role"],
                ordinal=int(r["ordinal"] or 0),
                notes=r["notes"] or "",
                part_name=r["part_name"] or "",
                part_slug=r["part_slug"] or "",
                part_kind=r["part_kind"] or "",
            )
            for r in rows
        ]

    def composition_tree(
        self,
        whole_ven_id: str,
        *,
        max_depth: int = COMPOSITION_DEPTH_DEFAULT,
        _ancestors: frozenset[str] | None = None,
    ) -> list[CompositionNode]:
        """
        Nested composition under *whole_ven_id*.

        ``max_depth=1`` → direct parts only (children empty).
        ``max_depth=4`` → recurse up to four edge hops (``deep`` mode).
        Cycles: include the edge with ``is_cycle=True`` and do not expand further.
        """
        if max_depth < 1:
            return []
        if self.get_ven(whole_ven_id) is None:
            return []
        ancestors = _ancestors if _ancestors is not None else frozenset()
        # Path of wholes already open; if this whole is on the path, caller handles cycle
        next_anc = ancestors | {whole_ven_id}
        out: list[CompositionNode] = []
        for p in self.list_ven_parts(whole_ven_id):
            is_cycle = p.part_ven_id in next_anc
            children: list[CompositionNode] = []
            if not is_cycle and max_depth > 1:
                children = self.composition_tree(
                    p.part_ven_id,
                    max_depth=max_depth - 1,
                    _ancestors=next_anc,
                )
            out.append(
                CompositionNode(part=p, children=children, is_cycle=is_cycle)
            )
        return out

    # ── Containment ──────────────────────────────────────────────────────

    def put_in(
        self,
        contained_instance_id: str,
        container_instance_id: str,
        slot: str = "interior",
    ) -> str:
        if contained_instance_id == container_instance_id:
            raise ValueError("Cannot contain self")
        # Move: one container at a time for MVP
        self.conn.execute(
            "DELETE FROM containment WHERE contained_instance_id = ?",
            (contained_instance_id,),
        )
        cid = new_id("cnt")
        self.conn.execute(
            """
            INSERT INTO containment(id, container_instance_id, contained_instance_id, slot)
            VALUES (?, ?, ?, ?)
            """,
            (cid, container_instance_id, contained_instance_id, slot),
        )
        self.conn.commit()
        return cid

    def contents(self, container_instance_id: str, slot: str | None = None) -> list[InstanceView]:
        if slot:
            rows = self.conn.execute(
                """
                SELECT i.id FROM containment c
                JOIN instances i ON i.id = c.contained_instance_id
                WHERE c.container_instance_id = ? AND c.slot = ?
                ORDER BY c.ordinal, c.created_at
                """,
                (container_instance_id, slot),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT i.id FROM containment c
                JOIN instances i ON i.id = c.contained_instance_id
                WHERE c.container_instance_id = ?
                ORDER BY c.slot, c.ordinal, c.created_at
                """,
                (container_instance_id,),
            ).fetchall()
        return [self.get_instance(r["id"]) for r in rows]  # type: ignore[misc]

    def container_of(self, instance_id: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT container_instance_id, slot FROM containment WHERE contained_instance_id = ?",
            (instance_id,),
        ).fetchone()
        if row is None:
            return None
        return row["container_instance_id"], row["slot"]

    # ── Links ────────────────────────────────────────────────────────────

    def link(
        self,
        from_instance_id: str,
        to_instance_id: str,
        label: str,
        link_type: str = "spatial",
        requirements: dict[str, Any] | None = None,
        bidirectional: bool = False,
        reverse_label: str | None = None,
    ) -> list[str]:
        if link_type not in LINK_TYPES:
            raise ValueError(f"Unknown link_type {link_type!r}")
        ids = [
            self._add_link(from_instance_id, to_instance_id, label, link_type, requirements)
        ]
        if bidirectional:
            ids.append(
                self._add_link(
                    to_instance_id,
                    from_instance_id,
                    reverse_label or label,
                    link_type,
                    requirements,
                )
            )
        return ids

    def _add_link(
        self,
        from_id: str,
        to_id: str,
        label: str,
        link_type: str,
        requirements: dict[str, Any] | None,
    ) -> str:
        lid = new_id("lnk")
        self.conn.execute(
            """
            INSERT INTO links(id, from_instance_id, to_instance_id, label, link_type, requirements_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (lid, from_id, to_id, label, link_type, json.dumps(requirements or {})),
        )
        self.conn.commit()
        return lid

    def exits(self, from_instance_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT l.*, i.id AS dest_id
            FROM links l
            JOIN instances i ON i.id = l.to_instance_id
            WHERE l.from_instance_id = ?
            ORDER BY l.link_type, l.label
            """,
            (from_instance_id,),
        ).fetchall()

    def find_exit(self, from_instance_id: str, label: str) -> sqlite3.Row | None:
        label_l = label.lower().strip()
        for ex in self.exits(from_instance_id):
            if ex["label"].lower() == label_l:
                return ex
        # partial match
        matches = [ex for ex in self.exits(from_instance_id) if label_l in ex["label"].lower()]
        if len(matches) == 1:
            return matches[0]
        return None

    def get_link(self, link_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM links WHERE id = ?", (link_id,)
        ).fetchone()

    def link_snapshot(self, link_id: str) -> dict[str, Any] | None:
        """Full row dict for undo-restore after delete."""
        row = self.get_link(link_id)
        if row is None:
            return None
        return {k: row[k] for k in row.keys()}

    def restore_links(self, snapshots: list[dict[str, Any]]) -> None:
        """Re-insert previously snapshotted link rows (same ids)."""
        for snap in snapshots:
            self.conn.execute(
                """
                INSERT INTO links(
                    id, from_instance_id, to_instance_id, label, link_type,
                    requirements_json, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap["id"],
                    snap["from_instance_id"],
                    snap["to_instance_id"],
                    snap["label"],
                    snap["link_type"],
                    snap.get("requirements_json") or "{}",
                    snap.get("meta_json") or "{}",
                    snap.get("created_at") or None,
                ),
            )
        self.conn.commit()

    def set_link_label(self, link_id: str, label: str) -> None:
        self.conn.execute(
            "UPDATE links SET label = ? WHERE id = ?",
            (label, link_id),
        )
        self.conn.commit()

    def reverse_exits(
        self, from_instance_id: str, to_instance_id: str
    ) -> list[sqlite3.Row]:
        """Exits on the destination that lead back to from_instance_id."""
        return self.conn.execute(
            """
            SELECT * FROM links
            WHERE from_instance_id = ? AND to_instance_id = ?
            ORDER BY label
            """,
            (to_instance_id, from_instance_id),
        ).fetchall()

    def adjacent_places(self, from_instance_id: str | None = None) -> list[InstanceView]:
        """Place instances one exit hop from here (or from_instance_id)."""
        loc_id = from_instance_id
        if loc_id is None:
            loc = self.player_location()
            if not loc:
                return []
            loc_id = loc.id
        out: list[InstanceView] = []
        seen: set[str] = set()
        for ex in self.exits(loc_id):
            dest = self.get_instance(ex["to_instance_id"])
            if dest is None or dest.ven_kind != "place":
                continue
            if dest.id in seen:
                continue
            seen.add(dest.id)
            out.append(dest)
        return out

    def resolve_adjacent_place(self, query: str) -> list[InstanceView]:
        """
        Match a neighboring place by exit label or place name/title.

        Exit labels win first (exact/partial via find_exit); then name matches
        among adjacent places only (not the whole world).
        """
        key = (query or "").strip()
        if not key:
            return []
        loc = self.player_location()
        if not loc:
            return []
        # Exit label → destination
        ex = self.find_exit(loc.id, key)
        if ex is not None:
            dest = self.get_instance(ex["to_instance_id"])
            if dest is not None and dest.ven_kind == "place":
                return [dest]
        # Place name among neighbors
        hits: list[InstanceView] = []
        for dest in self.adjacent_places(loc.id):
            if (
                names_match(key, dest.name)
                or names_match(key, dest.ven_name or "")
                or names_match(key, dest.ven_slug or "")
            ):
                hits.append(dest)
        return hits

    # ── Lore ─────────────────────────────────────────────────────────────

    def add_lore(
        self,
        subject_type: str,
        subject_id: str,
        body: str,
        title: str = "",
        timeline_instance_id: str | None = None,
        when_label: str | None = None,
        author: str = "builder",
    ) -> str:
        if subject_type not in ("ven", "instance"):
            raise ValueError("subject_type must be 'ven' or 'instance'")
        lid = new_id("lore")
        self.conn.execute(
            """
            INSERT INTO lore_revisions(
                id, subject_type, subject_id, timeline_instance_id,
                when_label, title, body, author
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lid,
                subject_type,
                subject_id,
                timeline_instance_id,
                when_label,
                title,
                body,
                author,
            ),
        )
        self.conn.commit()
        return lid

    def lore_for(
        self,
        subject_type: str,
        subject_id: str,
        timeline_instance_id: str | None = None,
    ) -> list[sqlite3.Row]:
        if timeline_instance_id:
            return self.conn.execute(
                """
                SELECT * FROM lore_revisions
                WHERE subject_type = ? AND subject_id = ?
                  AND (timeline_instance_id IS NULL OR timeline_instance_id = ?)
                ORDER BY created_at
                """,
                (subject_type, subject_id, timeline_instance_id),
            ).fetchall()
        return self.conn.execute(
            """
            SELECT * FROM lore_revisions
            WHERE subject_type = ? AND subject_id = ?
            ORDER BY created_at
            """,
            (subject_type, subject_id),
        ).fetchall()

    def search_lore(self, query: str) -> list[sqlite3.Row]:
        q = f"%{query}%"
        return self.conn.execute(
            """
            SELECT * FROM lore_revisions
            WHERE title LIKE ? OR body LIKE ? OR when_label LIKE ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (q, q, q),
        ).fetchall()

    # ── Timeline nodes + material history (story when) ─────────────────

    def ensure_timeline_node(
        self,
        timeline_instance_id: str,
        node_index: int,
        *,
        name: str = "",
        description: str = "",
    ) -> str:
        """Ensure numbered node exists on a timeline instance; return node row id."""
        if node_index < 0:
            raise ValueError("node_index must be >= 0")
        tl = self.get_instance(timeline_instance_id)
        if tl is None or (tl.ven_kind or "").lower() != "timeline":
            raise ValueError("timeline_instance_id must be a timeline instance")
        row = self.conn.execute(
            """
            SELECT id FROM timeline_nodes
            WHERE timeline_instance_id = ? AND node_index = ?
            """,
            (timeline_instance_id, node_index),
        ).fetchone()
        if row:
            return row["id"]
        nid = new_id("tnode")
        self.conn.execute(
            """
            INSERT INTO timeline_nodes(
                id, timeline_instance_id, node_index, name, description
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (nid, timeline_instance_id, node_index, name or "", description or ""),
        )
        self.conn.commit()
        return nid

    def list_timeline_nodes(self, timeline_instance_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM timeline_nodes
            WHERE timeline_instance_id = ?
            ORDER BY node_index
            """,
            (timeline_instance_id,),
        ).fetchall()

    def next_history_event_code(self) -> str:
        """Allocate the next shared history event code (HST-001, …)."""
        from .ids import format_ven_code

        max_n = 0
        for r in self.conn.execute(
            "SELECT event_code FROM history_entries "
            "WHERE event_code GLOB 'HST-[0-9]*'"
        ).fetchall():
            code = (r["event_code"] or "").strip().upper()
            if not code.startswith("HST-"):
                continue
            try:
                max_n = max(max_n, int(code.split("-", 1)[1]))
            except ValueError:
                pass
        return format_ven_code("HST", max_n + 1)

    def record_history(
        self,
        subject_type: str,
        subject_id: str,
        *,
        verb: str = "record",
        story_when: str = "@unknown",
        node_index: int | None = None,
        place_instance_id: str | None = None,
        place_name: str = "",
        realm_instance_id: str | None = None,
        realm_name: str = "",
        timeline_instance_id: str | None = None,
        timeline_name: str = "",
        note: str = "",
        event_code: str | None = None,
        commit: bool = True,
    ) -> str:
        """
        Append a story-when history row for a ven / instance / lore id.

        story_when is ``@N`` or ``@unknown``. When node_index is set and a
        timeline is known, the node row is ensured.

        Place / realm / timeline ids and display names are stored with the row
        (names snapshotted at craft time). *event_code* is shared across all
        legs of one logical act. If omitted, a new HST-NNN code is allocated.
        Returns the history row id.
        """
        if subject_type not in ("ven", "instance", "lore"):
            raise ValueError("subject_type must be ven, instance, or lore")
        sw = (story_when or "@unknown").strip() or "@unknown"
        if not sw.startswith("@"):
            sw = f"@{sw}"
        if sw.lower() == "@unknown":
            sw = "@unknown"
            node_index = None
        elif node_index is None and sw[1:].isdigit():
            node_index = int(sw[1:])
            sw = f"@{node_index}"
        if (
            node_index is not None
            and timeline_instance_id
            and sw != "@unknown"
        ):
            self.ensure_timeline_node(timeline_instance_id, node_index)
        code = (event_code or "").strip().upper() or self.next_history_event_code()
        hid = new_id("hist")
        self.conn.execute(
            """
            INSERT INTO history_entries(
                id, subject_type, subject_id, event_code,
                place_instance_id, place_name,
                realm_instance_id, realm_name,
                timeline_instance_id, timeline_name,
                story_when, node_index, verb, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hid,
                subject_type,
                subject_id,
                code,
                place_instance_id,
                place_name or "",
                realm_instance_id,
                realm_name or "",
                timeline_instance_id,
                timeline_name or "",
                sw,
                node_index,
                (verb or "record").strip() or "record",
                note or "",
            ),
        )
        if commit:
            self.conn.commit()
        return hid

    def record_history_event(
        self,
        legs: list[dict],
        *,
        story_when: str = "@unknown",
        node_index: int | None = None,
        place_instance_id: str | None = None,
        place_name: str = "",
        realm_instance_id: str | None = None,
        realm_name: str = "",
        timeline_instance_id: str | None = None,
        timeline_name: str = "",
        event_code: str | None = None,
    ) -> str:
        """
        Write one or more history legs that share a single event_code.

        Each leg dict: subject_type, subject_id, verb, note (optional),
        optional place/realm/timeline id or name overrides.
        Returns the shared event_code.
        """
        if not legs:
            raise ValueError("record_history_event needs at least one leg")
        code = (event_code or "").strip().upper() or self.next_history_event_code()
        for leg in legs:
            st = leg["subject_type"]
            sid = leg["subject_id"]
            self.record_history(
                st,
                sid,
                verb=leg.get("verb") or "record",
                story_when=story_when,
                node_index=node_index,
                place_instance_id=leg.get(
                    "place_instance_id", place_instance_id
                ),
                place_name=leg.get("place_name", place_name) or "",
                realm_instance_id=leg.get(
                    "realm_instance_id", realm_instance_id
                ),
                realm_name=leg.get("realm_name", realm_name) or "",
                timeline_instance_id=leg.get(
                    "timeline_instance_id", timeline_instance_id
                ),
                timeline_name=leg.get("timeline_name", timeline_name) or "",
                note=leg.get("note") or "",
                event_code=code,
                commit=False,
            )
        self.conn.commit()
        return code

    def history_for(
        self, subject_type: str, subject_id: str
    ) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM history_entries
            WHERE subject_type = ? AND subject_id = ?
            ORDER BY created_at
            """,
            (subject_type, subject_id),
        ).fetchall()

    def history_for_event(self, event_code: str) -> list[sqlite3.Row]:
        code = (event_code or "").strip().upper()
        if not code:
            return []
        return self.conn.execute(
            """
            SELECT * FROM history_entries
            WHERE upper(event_code) = ?
            ORDER BY created_at, id
            """,
            (code,),
        ).fetchall()

    def retime_history_event(
        self,
        event_code: str,
        *,
        story_when: str = "@unknown",
        node_index: int | None = None,
    ) -> tuple[str, int, list[dict]]:
        """
        Set story_when / node_index on every leg of a shared history event.

        Returns (canonical event_code, rows_updated, prior_legs) where each
        prior leg is ``{id, story_when, node_index}`` for undo.
        """
        code = (event_code or "").strip().upper()
        if not code:
            raise ValueError("event_code required")
        rows = self.history_for_event(code)
        if not rows:
            raise ValueError(f"No history event {code}")
        # Prefer code as stored (first row)
        code = (rows[0]["event_code"] or code).strip().upper()

        sw = (story_when or "@unknown").strip() or "@unknown"
        if not sw.startswith("@"):
            sw = f"@{sw}"
        if sw.lower() == "@unknown":
            sw = "@unknown"
            ni: int | None = None
        else:
            if node_index is not None:
                ni = int(node_index)
                sw = f"@{ni}"
            elif sw[1:].isdigit():
                ni = int(sw[1:])
                sw = f"@{ni}"
            else:
                sw = "@unknown"
                ni = None

        prior: list[dict] = []
        timeline_ids: set[str] = set()
        for r in rows:
            prior.append(
                {
                    "id": r["id"],
                    "story_when": r["story_when"] or "@unknown",
                    "node_index": r["node_index"],
                }
            )
            tl = r["timeline_instance_id"]
            if tl and ni is not None:
                timeline_ids.add(tl)

        for tl_id in timeline_ids:
            self.ensure_timeline_node(tl_id, ni)  # type: ignore[arg-type]

        self.conn.execute(
            """
            UPDATE history_entries
            SET story_when = ?, node_index = ?
            WHERE upper(event_code) = ?
            """,
            (sw, ni, code),
        )
        self.conn.commit()
        return code, len(rows), prior

    def restore_history_event_times(self, priors: list[dict]) -> None:
        """Undo a retime: restore per-row story_when / node_index from prior list."""
        for p in priors:
            self.conn.execute(
                """
                UPDATE history_entries
                SET story_when = ?, node_index = ?
                WHERE id = ?
                """,
                (
                    p.get("story_when") or "@unknown",
                    p.get("node_index"),
                    p["id"],
                ),
            )
        self.conn.commit()

    # ── Text editor save history (<< / <<studio) ─────────────────────────

    def add_text_revision(
        self,
        subject_type: str,
        subject_id: str,
        body: str,
        *,
        field: str = "body",
        title: str = "",
        format: str = "plain",
        author: str = "builder",
        note: str = "",
    ) -> str:
        """Append a full-body snapshot from an editor save."""
        rid = new_id("trev")
        self.conn.execute(
            """
            INSERT INTO text_revisions(
                id, subject_type, subject_id, field, title, body,
                format, author, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                subject_type,
                subject_id,
                field,
                title or "",
                body if body is not None else "",
                format if format in ("plain", "studio") else "plain",
                author,
                note or "",
            ),
        )
        self.conn.commit()
        return rid

    def list_text_revisions(
        self,
        subject_type: str,
        subject_id: str,
        *,
        field: str | None = None,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        if field:
            return self.conn.execute(
                """
                SELECT * FROM text_revisions
                WHERE subject_type = ? AND subject_id = ? AND field = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (subject_type, subject_id, field, limit),
            ).fetchall()
        return self.conn.execute(
            """
            SELECT * FROM text_revisions
            WHERE subject_type = ? AND subject_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (subject_type, subject_id, limit),
        ).fetchall()

    def get_text_revision(self, revision_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM text_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()

    def find_text_revision(self, query: str) -> sqlite3.Row | None:
        """Resolve by full id or unique short prefix."""
        q = (query or "").strip()
        if not q:
            return None
        row = self.get_text_revision(q)
        if row:
            return row
        rows = self.conn.execute(
            "SELECT * FROM text_revisions WHERE id LIKE ? ORDER BY created_at DESC",
            (f"{q}%",),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]
        return None

    # ── Lookups ──────────────────────────────────────────────────────────

    def get_ven(self, ven_id: str) -> VenView | None:
        row = self.conn.execute("SELECT * FROM vens WHERE id = ?", (ven_id,)).fetchone()
        if not row:
            return None
        meta = json.loads(row["meta_json"] or "{}")
        subtype = meta.get("subtype")
        if subtype is not None:
            subtype = str(subtype).strip() or None
        parent_ven_id = None
        try:
            parent_ven_id = row["parent_ven_id"]
        except (IndexError, KeyError):
            parent_ven_id = None
        code = None
        try:
            code = row["code"]
        except (IndexError, KeyError):
            code = None
        if code is not None:
            code = str(code).strip() or None
        return VenView(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            kind=row["kind"],
            description=row["description"],
            is_prime=bool(row["is_prime"]),
            tags=json.loads(row["tags_json"] or "[]"),
            subtype=subtype,
            meta=meta,
            parent_ven_id=parent_ven_id,
            code=code,
        )

    def _set_ven_meta(self, ven_id: str, meta: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE vens SET meta_json = ? WHERE id = ?",
            (json.dumps(meta), ven_id),
        )
        self.conn.commit()

    def get_wiki_links(self, ven_id: str) -> list[str]:
        """VEN ids listed as wiki sub-links on this prime (meta wiki_links)."""
        ven = self.get_ven(ven_id)
        if ven is None:
            return []
        meta = ven.meta or {}
        raw = meta.get("wiki_links") or []
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for x in raw:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out

    def add_wiki_link(self, from_ven_id: str, to_ven_id: str) -> None:
        """Append a sub-link (must be two existing VEN ids)."""
        if self.get_ven(from_ven_id) is None:
            raise ValueError(f"No VEN {from_ven_id}")
        if self.get_ven(to_ven_id) is None:
            raise ValueError(f"No VEN {to_ven_id}")
        if from_ven_id == to_ven_id:
            raise ValueError("Cannot wiki-link a VEN to itself")
        ven = self.get_ven(from_ven_id)
        assert ven is not None
        meta = dict(ven.meta or {})
        links = list(self.get_wiki_links(from_ven_id))
        if to_ven_id not in links:
            links.append(to_ven_id)
        meta["wiki_links"] = links
        # preserve subtype in meta if present
        if ven.subtype:
            meta["subtype"] = ven.subtype
        self._set_ven_meta(from_ven_id, meta)

    def remove_wiki_link(self, from_ven_id: str, to_ven_id: str) -> bool:
        """Remove sub-link; returns True if it was present."""
        ven = self.get_ven(from_ven_id)
        if ven is None:
            raise ValueError(f"No VEN {from_ven_id}")
        links = self.get_wiki_links(from_ven_id)
        if to_ven_id not in links:
            return False
        meta = dict(ven.meta or {})
        meta["wiki_links"] = [x for x in links if x != to_ven_id]
        if ven.subtype:
            meta["subtype"] = ven.subtype
        self._set_ven_meta(from_ven_id, meta)
        return True

    def get_ven_by_slug(self, slug: str) -> VenView | None:
        key = slug.strip()
        row = self.conn.execute("SELECT id FROM vens WHERE slug = ?", (key,)).fetchone()
        if row:
            return self.get_ven(row["id"])
        cute = cute_name(key)
        if cute != key:
            row = self.conn.execute("SELECT id FROM vens WHERE slug = ?", (cute,)).fetchone()
            if row:
                return self.get_ven(row["id"])
        # case-insensitive fallback
        row = self.conn.execute(
            "SELECT id FROM vens WHERE upper(slug) = upper(?)", (key,)
        ).fetchone()
        return self.get_ven(row["id"]) if row else None

    def get_instance(self, instance_id: str) -> InstanceView | None:
        row = self.conn.execute(
            """
            SELECT i.*, v.name AS ven_name, v.kind AS ven_kind, v.slug AS ven_slug,
                   v.description AS ven_description, v.meta_json AS ven_meta_json,
                   v.code AS ven_code
            FROM instances i
            JOIN vens v ON v.id = i.ven_id
            WHERE i.id = ?
            """,
            (instance_id,),
        ).fetchone()
        if not row:
            return None
        name = row["name_override"] or row["ven_name"]
        desc = row["description_override"] if row["description_override"] is not None else row["ven_description"]
        meta = json.loads(row["ven_meta_json"] or "{}")
        subtype = meta.get("subtype")
        if subtype is not None:
            subtype = str(subtype).strip() or None
        ven_code = None
        try:
            ven_code = row["ven_code"]
        except (IndexError, KeyError):
            ven_code = None
        if ven_code is not None:
            ven_code = parse_ven_code(str(ven_code)) or str(ven_code).strip() or None
        return InstanceView(
            id=row["id"],
            ven_id=row["ven_id"],
            ven_name=row["ven_name"],
            ven_kind=row["ven_kind"],
            ven_slug=row["ven_slug"],
            name=name,
            description=desc,
            realm_instance_id=row["realm_instance_id"],
            timeline_instance_id=row["timeline_instance_id"],
            state=json.loads(row["state_json"] or "{}"),
            ven_subtype=subtype,
            ven_code=ven_code,
        )

    def find_instances_by_name(self, name: str, kind: str | None = None) -> list[InstanceView]:
        rows = self.conn.execute(
            """
            SELECT i.id, v.name AS ven_name, i.name_override, v.kind
            FROM instances i
            JOIN vens v ON v.id = i.ven_id
            """
        ).fetchall()
        out: list[InstanceView] = []
        for r in rows:
            display = r["name_override"] or r["ven_name"]
            # Match display title or underlying prime name (after renames)
            if not (
                names_match(name, display) or names_match(name, r["ven_name"] or "")
            ):
                continue
            if kind and r["kind"] != kind:
                continue
            inst = self.get_instance(r["id"])
            if inst:
                out.append(inst)
        return out

    def list_vens(self, kind: str | None = None) -> list[VenView]:
        if kind:
            rows = self.conn.execute(
                "SELECT id FROM vens WHERE kind = ? ORDER BY name", (kind,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT id FROM vens ORDER BY kind, name").fetchall()
        return [self.get_ven(r["id"]) for r in rows]  # type: ignore[misc]

    def find_ven(self, slug_or_name: str) -> VenView | None:
        """Resolve a prime VEN by code, slug, or name (relaxed typing)."""
        key = slug_or_name.strip()
        if not key:
            return None
        by_code = self.get_ven_by_code(key)
        if by_code:
            return by_code
        by_slug = self.get_ven_by_slug(key)
        if by_slug:
            return by_slug
        strict = [
            v
            for v in self.list_vens()
            if cute_name(key) == cute_name(v.name) or cute_name(key) == cute_name(v.slug)
        ]
        if len(strict) == 1:
            return strict[0]
        if len(strict) > 1:
            return None
        partial = [
            v
            for v in self.list_vens()
            if names_match(key, v.name)
            or names_match(key, v.slug)
            or (v.code and names_match(key, v.code))
        ]
        if len(partial) == 1:
            return partial[0]
        return None

    # ── Player / movement ────────────────────────────────────────────────

    def player_id(self) -> str | None:
        return get_meta(self.conn, "player_instance_id")

    def set_player(self, instance_id: str) -> None:
        if self.get_instance(instance_id) is None:
            raise ValueError("Player instance does not exist")
        set_meta(self.conn, "player_instance_id", instance_id)

    def player_location(self) -> InstanceView | None:
        pid = self.player_id()
        if not pid:
            return None
        cont = self.container_of(pid)
        if not cont:
            return None
        return self.get_instance(cont[0])

    def move_player(self, to_place_instance_id: str) -> None:
        pid = self.player_id()
        if not pid:
            raise ValueError("No player set")
        dest = self.get_instance(to_place_instance_id)
        if dest is None or dest.ven_kind != "place":
            raise ValueError("Destination must be a place instance")
        self.put_in(pid, to_place_instance_id, slot="interior")

    _TAKEABLE_KINDS = (
        "thing",
        "folio",
        "bin",  # bags / furniture you can pick up (not place-scale by default)
        "sense",
        "symbol",
        "ticket",  # TDF slips
        # legacy kinds if any linger
        "container",
        "object",
        "material",
        "archetype",
        "feeling",
        "concept",
        "book",
        "other",
        "goal",
        "desire",
        "purpose",
        "event",
    )

    def is_reachable(self, instance_id: str) -> bool:
        """True if the instance is the place, the player, or nested inside either."""
        loc = self.player_location()
        pid = self.player_id()
        seen: set[str] = set()
        cur: str | None = instance_id
        while cur and cur not in seen:
            seen.add(cur)
            if loc and cur == loc.id:
                return True
            if pid and cur == pid:
                return True
            cont = self.container_of(cur)
            if not cont:
                break
            cur = cont[0]
        return False

    def takeable(self, item: InstanceView) -> bool:
        return item.ven_kind in self._TAKEABLE_KINDS

    # Mythic landfill for soft-despawn (instances keep lore/books; no hard delete)
    LOST_DEPT_NAME = "Lost Dept"
    LOST_DEPT_SLUG = "LOST-DEPT"

    def ensure_lost_dept(self) -> InstanceView:
        """Ensure the Lost Dept place prime + instance (landfill for unplaced things)."""
        ven = self.get_ven_by_slug(self.LOST_DEPT_SLUG)
        if ven is None:
            ven = self.find_ven(self.LOST_DEPT_NAME)
        if ven is None or ven.kind != "place":
            ven_id = self.create_ven(
                self.LOST_DEPT_NAME,
                "place",
                description=(
                    "A mythic warehouse of things that slipped out of play. "
                    "Nothing is destroyed here — only shelved out of reach. "
                    "Reclaim what you still need; leave the rest."
                ),
                tags=["mythic", "landfill", "lost"],
            )
            ven = self.get_ven(ven_id)
            assert ven is not None
        # Prefer existing instance of this prime
        row = self.conn.execute(
            "SELECT id FROM instances WHERE ven_id = ? ORDER BY created_at LIMIT 1",
            (ven.id,),
        ).fetchone()
        if row:
            inst = self.get_instance(row["id"])
            assert inst is not None
            return inst
        inst_id = self.instantiate(ven.id)
        inst = self.get_instance(inst_id)
        assert inst is not None
        return inst

    def is_lost_dept(self, instance_id: str) -> bool:
        inst = self.get_instance(instance_id)
        if inst is None:
            return False
        return (
            cute_name(inst.ven_slug or "") == self.LOST_DEPT_SLUG
            or cute_name(inst.ven_name or "") == cute_name(self.LOST_DEPT_NAME)
            or cute_name(inst.name or "") == cute_name(self.LOST_DEPT_NAME)
        )

    def lose_instance(self, instance_id: str) -> tuple[str, str]:
        """
        Soft-despawn: move instance into Lost Dept interior.

        Returns (lost_dept_instance_id, prior_container_id_or_empty).
        """
        item = self.get_instance(instance_id)
        if item is None:
            raise ValueError("No such item")
        pid = self.player_id()
        if pid and instance_id == pid:
            raise ValueError("Cannot lose yourself")
        if item.ven_kind == "place":
            raise ValueError("Cannot lose a place (including Lost Dept)")
        if item.ven_kind in ("realm", "timeline"):
            raise ValueError(f"Cannot lose a {item.ven_kind} layer")
        if self.is_lost_dept(instance_id):
            raise ValueError("Cannot lose the Lost Dept")
        # Don't lose something that contains the player
        if pid:
            cont = self.container_of(pid)
            while cont:
                if cont[0] == instance_id:
                    raise ValueError("Cannot lose something that holds you")
                cont = self.container_of(cont[0])
        if not self.takeable(item):
            raise ValueError(f"Cannot lose a {item.ven_kind}")
        prior = self.container_of(instance_id)
        prior_id = prior[0] if prior else ""
        dept = self.ensure_lost_dept()
        if prior and prior[0] == dept.id:
            raise ValueError("That is already in Lost Dept")
        self.put_in(instance_id, dept.id, slot="interior")
        return dept.id, prior_id

    def reclaim_instance(self, instance_id: str) -> None:
        """Pull an instance out of Lost Dept into player inventory."""
        pid = self.player_id()
        if not pid:
            raise ValueError("No player set")
        item = self.get_instance(instance_id)
        if item is None:
            raise ValueError("No such item")
        cont = self.container_of(instance_id)
        if cont is None or not self.is_lost_dept(cont[0]):
            raise ValueError("That is not in Lost Dept")
        if not self.takeable(item):
            raise ValueError(f"Cannot reclaim a {item.ven_kind}")
        self.put_in(instance_id, pid, slot="inventory")

    def list_lost_contents(self) -> list[InstanceView]:
        """Direct contents of Lost Dept (the landfill shelf)."""
        dept = self.ensure_lost_dept()
        return self.contents(dept.id)

    def find_lost_named(self, name: str) -> InstanceView | None:
        """Resolve a unique name among Lost Dept contents (including nested one level)."""
        key = (name or "").strip()
        if not key:
            return None
        hits: list[InstanceView] = []
        for c in self.list_lost_contents():
            if names_match(key, c.name) or names_match(key, c.ven_name) or names_match(
                key, c.ven_slug
            ):
                hits.append(c)
            for inner in self.contents(c.id):
                if names_match(key, inner.name) or names_match(
                    key, inner.ven_name
                ) or names_match(key, inner.ven_slug):
                    hits.append(inner)
        if len(hits) == 1:
            return hits[0]
        return None

    def take(self, item_instance_id: str) -> None:
        """Take from the current place floor into inventory."""
        pid = self.player_id()
        if not pid:
            raise ValueError("No player set")
        loc = self.player_location()
        if loc is None:
            raise ValueError("Player has no location")
        cont = self.container_of(item_instance_id)
        if cont is None or cont[0] != loc.id:
            raise ValueError("That is not on the ground here (try: take <thing> from <box>)")
        item = self.get_instance(item_instance_id)
        if item is None:
            raise ValueError("No such item")
        if not self.takeable(item):
            raise ValueError(f"Cannot take a {item.ven_kind}")
        self.put_in(item_instance_id, pid, slot="inventory")

    def take_from(self, item_instance_id: str, container_instance_id: str) -> None:
        """Move an item out of a reachable container into inventory."""
        pid = self.player_id()
        if not pid:
            raise ValueError("No player set")
        if item_instance_id == container_instance_id:
            raise ValueError("Cannot take a container from itself")
        if not self.is_reachable(container_instance_id):
            raise ValueError("That container is not here")
        cont = self.container_of(item_instance_id)
        if cont is None or cont[0] != container_instance_id:
            raise ValueError("That is not inside the container")
        item = self.get_instance(item_instance_id)
        if item is None:
            raise ValueError("No such item")
        if not self.takeable(item):
            raise ValueError(f"Cannot take a {item.ven_kind}")
        # Don't pull the player into a paradox
        if item_instance_id == pid:
            raise ValueError("Cannot take yourself")
        self.put_in(item_instance_id, pid, slot="inventory")

    def find_in_container(self, container_instance_id: str, name: str) -> InstanceView | None:
        """Find a direct content of a container by name."""
        for c in self.contents(container_instance_id):
            if names_match(name, c.name):
                return c
        return None

    def drop(self, item_instance_id: str) -> None:
        pid = self.player_id()
        if not pid:
            raise ValueError("No player set")
        loc = self.player_location()
        if loc is None:
            raise ValueError("Player has no location")
        cont = self.container_of(item_instance_id)
        if cont is None or cont[0] != pid:
            raise ValueError("You are not carrying that")
        self.put_in(item_instance_id, loc.id, slot="interior")

    def inventory(self) -> list[InstanceView]:
        pid = self.player_id()
        if not pid:
            return []
        return self.contents(pid, slot="inventory")

    def describe_place(self, place: InstanceView) -> dict[str, Any]:
        """
        Partition room contents for look (lean kinds):

        - person (not archetype) → Here (not the player)
        - thing / folio / bin → Things (legacy kind partitions; look uses placement)
        - sense with subtype event → Happened Here
        - person/archetype → Force
        - sense, symbol, place, … → Also present
        """
        here = self.contents(place.id)
        pid = self.player_id()

        def _sub(c: InstanceView) -> str:
            return (c.ven_subtype or "").strip().lower()

        people = [
            c
            for c in here
            if c.ven_kind == "person"
            and _sub(c) != "archetype"
            and c.id != pid
        ]
        objects = [
            c
            for c in here
            if c.ven_kind
            in ("thing", "folio", "bin", "container", "object", "material", "book")
        ]
        events = [
            c
            for c in here
            if c.ven_kind == "event"
            or (c.ven_kind == "sense" and _sub(c) == "event")  # legacy fold
        ]
        forces = [
            c
            for c in here
            if (c.ven_kind == "person" and _sub(c) == "archetype")
            or c.ven_kind == "archetype"
        ]
        claimed_ids = {c.id for c in people + objects + events + forces}
        other = [c for c in here if c.id not in claimed_ids and c.id != pid]
        exits = self.exits(place.id)
        realm = self.get_instance(place.realm_instance_id) if place.realm_instance_id else None
        timeline = (
            self.get_instance(place.timeline_instance_id) if place.timeline_instance_id else None
        )
        return {
            "place": place,
            "realm": realm,
            "timeline": timeline,
            "people": people,
            "objects": objects,
            "events": events,
            "forces": forces,
            "other": other,
            "exits": exits,
            "lore": self.lore_for("instance", place.id, place.timeline_instance_id),
        }

    def get_description_override(self, instance_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT description_override FROM instances WHERE id = ?",
            (instance_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No instance {instance_id}")
        return row["description_override"]

    def set_description(self, instance_id: str, description: str | None) -> None:
        """Set description_override. Pass None to clear (fall back to VEN description)."""
        self.conn.execute(
            "UPDATE instances SET description_override = ? WHERE id = ?",
            (description, instance_id),
        )
        self.conn.commit()

    def delete_links(self, link_ids: list[str]) -> None:
        for lid in link_ids:
            self.conn.execute("DELETE FROM links WHERE id = ?", (lid,))
        self.conn.commit()

    def delete_lore(self, lore_id: str) -> None:
        self.conn.execute("DELETE FROM lore_revisions WHERE id = ?", (lore_id,))
        self.conn.commit()

    def delete_instance(self, instance_id: str) -> None:
        """Delete an instance (cascades containment/links that reference it)."""
        self.conn.execute("DELETE FROM instances WHERE id = ?", (instance_id,))
        self.conn.commit()

    def delete_ven(self, ven_id: str) -> None:
        self.conn.execute("DELETE FROM vens WHERE id = ?", (ven_id,))
        self.conn.commit()

    # ── Realm / timeline (layer) management ──────────────────────────────

    def ensure_layer_instance(self, ven_id: str) -> str:
        """Return the first instance of a realm/timeline VEN, creating one if needed."""
        ven = self.get_ven(ven_id)
        if ven is None:
            raise ValueError(f"No VEN {ven_id}")
        if ven.kind not in ("realm", "timeline"):
            raise ValueError(f"VEN {ven.name} is {ven.kind}, not realm/timeline")
        row = self.conn.execute(
            "SELECT id FROM instances WHERE ven_id = ? ORDER BY created_at LIMIT 1",
            (ven_id,),
        ).fetchone()
        if row:
            return row["id"]
        return self.instantiate(ven_id)

    def current_layer_instance(self, kind: str) -> InstanceView | None:
        """Realm/timeline layer instance for the place the player stands in."""
        if kind not in ("realm", "timeline"):
            raise ValueError("kind must be realm or timeline")
        loc = self.player_location()
        if loc is None:
            return None
        iid = (
            loc.realm_instance_id if kind == "realm" else loc.timeline_instance_id
        )
        if not iid:
            return None
        return self.get_instance(iid)

    def resolve_layer(self, kind: str, name: str) -> InstanceView | None:
        """Resolve a realm or timeline layer instance by VEN name/slug."""
        if kind not in ("realm", "timeline"):
            raise ValueError("kind must be realm or timeline")
        key = name.strip()
        if not key:
            return None
        ven = self.find_ven(key)
        if ven is not None:
            if ven.kind != kind:
                return None
            return self.get_instance(self.ensure_layer_instance(ven.id))
        # match among existing layer instances by display name
        hits: list[InstanceView] = []
        for inst in self.list_instances_of_kind(kind):
            if names_match(key, inst.name) or names_match(key, inst.ven_slug):
                hits.append(inst)
        if len(hits) == 1:
            return hits[0]
        return None

    def list_instances_of_kind(self, kind: str) -> list[InstanceView]:
        rows = self.conn.execute(
            """
            SELECT i.id FROM instances i
            JOIN vens v ON v.id = i.ven_id
            WHERE v.kind = ?
            ORDER BY v.name, i.created_at
            """,
            (kind,),
        ).fetchall()
        return [self.get_instance(r["id"]) for r in rows]  # type: ignore[misc]

    def list_layer_catalog(self, kind: str) -> list[dict[str, Any]]:
        """List realm/timeline primes with their layer instance ids."""
        out: list[dict[str, Any]] = []
        for ven in self.list_vens(kind):
            row = self.conn.execute(
                "SELECT id FROM instances WHERE ven_id = ? ORDER BY created_at LIMIT 1",
                (ven.id,),
            ).fetchone()
            inst = self.get_instance(row["id"]) if row else None
            places_n = 0
            if inst:
                col = "realm_instance_id" if kind == "realm" else "timeline_instance_id"
                places_n = self.conn.execute(
                    f"""
                    SELECT COUNT(*) AS n FROM instances i
                    JOIN vens v ON v.id = i.ven_id
                    WHERE v.kind = 'place' AND i.{col} = ?
                    """,
                    (inst.id,),
                ).fetchone()["n"]
            out.append(
                {
                    "ven": ven,
                    "instance": inst,
                    "place_count": places_n,
                }
            )
        return out

    def set_instance_coords(
        self,
        instance_id: str,
        *,
        realm_instance_id: str | None | object = ...,
        timeline_instance_id: str | None | object = ...,
    ) -> None:
        """Assign realm and/or timeline layer on any instance.

        Pass Ellipsis (...) to leave a field unchanged; None to clear.
        """
        inst = self.get_instance(instance_id)
        if inst is None:
            raise ValueError(f"No instance {instance_id}")

        new_realm = inst.realm_instance_id
        new_tl = inst.timeline_instance_id

        if realm_instance_id is not ...:
            if realm_instance_id is not None:
                r = self.get_instance(str(realm_instance_id))
                if r is None or r.ven_kind != "realm":
                    raise ValueError("realm_instance_id must be a realm instance")
            new_realm = None if realm_instance_id is None else str(realm_instance_id)

        if timeline_instance_id is not ...:
            if timeline_instance_id is not None:
                t = self.get_instance(str(timeline_instance_id))
                if t is None or t.ven_kind != "timeline":
                    raise ValueError("timeline_instance_id must be a timeline instance")
            new_tl = None if timeline_instance_id is None else str(timeline_instance_id)

        self.conn.execute(
            """
            UPDATE instances
            SET realm_instance_id = ?, timeline_instance_id = ?
            WHERE id = ?
            """,
            (new_realm, new_tl, instance_id),
        )
        self.conn.commit()

    def create_layer(
        self,
        kind: str,
        name: str,
        description: str = "",
    ) -> tuple[str, str]:
        """Create a realm or timeline VEN + ensure a layer instance. Returns (ven_id, inst_id)."""
        if kind not in ("realm", "timeline"):
            raise ValueError("kind must be realm or timeline")
        # reuse existing VEN if name already exists for that kind
        existing = self.find_ven(name)
        if existing and existing.kind == kind:
            inst_id = self.ensure_layer_instance(existing.id)
            return existing.id, inst_id
        if existing and existing.kind != kind:
            raise ValueError(f"{existing.name} already exists as {existing.kind}")
        ven_id = self.create_ven(name, kind, description=description)
        inst_id = self.ensure_layer_instance(ven_id)
        return ven_id, inst_id

    def coords_of(self, inst: InstanceView) -> dict[str, Any]:
        """Readable dimensional/temporal coordinates for an instance."""
        realm = self.get_instance(inst.realm_instance_id) if inst.realm_instance_id else None
        timeline = (
            self.get_instance(inst.timeline_instance_id) if inst.timeline_instance_id else None
        )
        return {
            "instance": inst,
            "realm": realm,
            "timeline": timeline,
            "realm_name": realm.name if realm else "—",
            "timeline_name": timeline.name if timeline else "—",
            "label": f"{realm.name if realm else '—'} / {timeline.name if timeline else '—'}",
        }

    def places_on_timeline(self, timeline_instance_id: str) -> list[InstanceView]:
        rows = self.conn.execute(
            """
            SELECT i.id FROM instances i
            JOIN vens v ON v.id = i.ven_id
            WHERE v.kind = 'place' AND i.timeline_instance_id = ?
            ORDER BY v.name
            """,
            (timeline_instance_id,),
        ).fetchall()
        return [self.get_instance(r["id"]) for r in rows]  # type: ignore[misc]

    def places_in_realm(self, realm_instance_id: str) -> list[InstanceView]:
        rows = self.conn.execute(
            """
            SELECT i.id FROM instances i
            JOIN vens v ON v.id = i.ven_id
            WHERE v.kind = 'place' AND i.realm_instance_id = ?
            ORDER BY v.name
            """,
            (realm_instance_id,),
        ).fetchall()
        return [self.get_instance(r["id"]) for r in rows]  # type: ignore[misc]

    def _is_under(self, instance_id: str, ancestor_id: str) -> bool:
        """True if *instance_id* is *ancestor_id* or nested inside it."""
        seen: set[str] = set()
        cur: str | None = instance_id
        while cur and cur not in seen:
            if cur == ancestor_id:
                return True
            seen.add(cur)
            cont = self.container_of(cur)
            if not cont:
                break
            cur = cont[0]
        return False

    def resolve_here_candidates(self, name: str = "") -> list[InstanceView]:
        """All instances in place, inventory, and nested inside reachable containers.

        Walks containment so a book (or other thing) inside a box on the floor
        or in a carried pack is still a resolve candidate — e.g. ``book open``.
        The player avatar itself is not listed as a candidate.
        """
        loc = self.player_location()
        pid = self.player_id()
        candidates: list[InstanceView] = []
        seen: set[str] = set()

        def add_tree(root_id: str) -> None:
            for c in self.contents(root_id):
                if c.id in seen:
                    continue
                seen.add(c.id)
                # Do not surface the player as a named target; still walk inv
                if pid and c.id == pid:
                    add_tree(c.id)
                    continue
                candidates.append(c)
                add_tree(c.id)

        if loc:
            add_tree(loc.id)
        if pid and pid not in seen:
            # Player not under place (edge cases) — still include inventory tree
            add_tree(pid)
        return candidates

    def resolve_here_named(
        self,
        name: str,
        *,
        kind: str | None = None,
        allow_ambiguous: bool = False,
    ) -> InstanceView | None:
        """
        Find something by name/ref in current place or inventory.

        Supports qualifiers: `here`, `inv`, `#FIELD-NOTES-0001` / `#0001`.
        Multiple matches → None (unless allow_ambiguous, then first — discouraged).
        Use resolve_here_matches + format_ambiguity for player-facing errors.
        """
        matches = self.resolve_here_matches(name, kind=kind)
        if len(matches) == 1:
            return matches[0]
        if allow_ambiguous and matches:
            return matches[0]
        return None

    def resolve_here_matches(
        self,
        name: str,
        *,
        kind: str | None = None,
    ) -> list[InstanceView]:
        """All reachable matches for a query (may be empty or many)."""
        # TDF codes before VEN short-ref parsing (TDF-######## looks like a ref)
        tdf_direct = parse_tdf_code((name or "").strip().lstrip("#"))
        if tdf_direct:
            candidates = self.resolve_here_candidates()
            if kind:
                candidates = [c for c in candidates if c.ven_kind == kind]
            return [
                c
                for c in candidates
                if parse_tdf_code(str((c.state or {}).get(TDF_CODE_KEY) or ""))
                == tdf_direct
            ]

        base, where, ref = parse_resolve_query(name)
        candidates = self.resolve_here_candidates()
        if kind:
            candidates = [c for c in candidates if c.ven_kind == kind]

        # Filter by location qualifier (includes nested under place / inv trees)
        if where == "here":
            loc = self.player_location()
            pid = self.player_id()
            if not loc:
                return []
            candidates = [
                c
                for c in candidates
                if self._is_under(c.id, loc.id)
                and not (pid and self._is_under(c.id, pid))
            ]
        elif where == "inv":
            pid = self.player_id()
            if not pid:
                return []
            candidates = [
                c for c in candidates if self._is_under(c.id, pid) and c.id != pid
            ]

        # Match by short ref alone or with base (digits or SLUG-NNNN)
        if ref:
            by_ref = [c for c in candidates if self.short_ref_matches(c.id, ref)]
            if base:
                by_ref = [
                    c
                    for c in by_ref
                    if names_match(base, c.name)
                    or names_match(base, c.ven_slug)
                    or names_match(base, c.ven_name)
                ]
            return by_ref

        if not base:
            return []

        # TDF codes (printed tickets): TDF-48291037
        tdf = parse_tdf_code(base)
        if tdf:
            by_tdf = [
                c
                for c in candidates
                if parse_tdf_code(str((c.state or {}).get(TDF_CODE_KEY) or "")) == tdf
            ]
            if by_tdf:
                return by_tdf

        # Whole base is a composite short ref (e.g. FIELD-NOTES-0001)
        maybe_ref = parse_instance_ref_token(base)
        if maybe_ref and "-" in maybe_ref:
            by_ref = [c for c in candidates if self.short_ref_matches(c.id, maybe_ref)]
            if by_ref:
                return by_ref

        # Whole-name / whole-token match only (see ids.names_match).
        # No in-token substring: "q1" does not hit "Q1G1".
        return [
            c
            for c in candidates
            if names_match(base, c.name or "")
            or names_match(base, c.ven_slug or "")
            or names_match(base, c.ven_name or "")
        ]

    # ── Dialogs (completed talk transcripts) ─────────────────────────────

    def dialog_slug_of(self, row: sqlite3.Row | dict[str, Any]) -> str:
        """Player-facing cute handle; falls back to opaque id if missing."""
        try:
            slug = row["slug"]
        except (KeyError, IndexError, TypeError):
            slug = None
        if slug and str(slug).strip():
            return str(slug).strip()
        try:
            return str(row["id"])
        except (KeyError, IndexError, TypeError):
            return ""

    def get_dialog_by_slug(self, slug: str) -> sqlite3.Row | None:
        key = (slug or "").strip()
        if not key:
            return None
        # Exact then case-insensitive cute match
        row = self.conn.execute(
            "SELECT * FROM dialogs WHERE slug = ?", (key,)
        ).fetchone()
        if row:
            return row
        cute = cute_name(key)
        return self.conn.execute(
            "SELECT * FROM dialogs WHERE upper(slug) = ?",
            (cute,),
        ).fetchone()

    def allocate_dialog_slug(self, title: str) -> str:
        """Unique cute slug from title: FIRST-MEETING, FIRST-MEETING-2, …"""
        base = cute_name(title or "") or "DIALOG"
        if base in ("UNNAMED", ""):
            base = "DIALOG"
        candidate = base
        n = 2
        while self.get_dialog_by_slug(candidate) is not None:
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    def save_dialog(
        self,
        *,
        title: str,
        when_label: str | None,
        place_instance_id: str | None,
        timeline_instance_id: str | None,
        speaker_a_id: str | None,
        speaker_b_id: str | None,
        speaker_a_name: str,
        speaker_b_name: str,
        transcript: str,
    ) -> str:
        did = new_id("dlg")
        slug = self.allocate_dialog_slug(title or "")
        self.conn.execute(
            """
            INSERT INTO dialogs(
                id, slug, title, when_label, place_instance_id, timeline_instance_id,
                speaker_a_id, speaker_b_id, speaker_a_name, speaker_b_name, transcript
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                slug,
                title or "",
                when_label,
                place_instance_id,
                timeline_instance_id,
                speaker_a_id,
                speaker_b_id,
                speaker_a_name,
                speaker_b_name,
                transcript,
            ),
        )
        self.conn.commit()
        return did

    def list_dialogs(
        self,
        limit: int = 50,
        *,
        place_instance_id: str | None = None,
    ) -> list[sqlite3.Row]:
        """
        Completed dialogs, newest first.

        If ``place_instance_id`` is set, only transcripts that finished in
        that place (dialogs.place_instance_id).
        """
        if place_instance_id:
            return self.conn.execute(
                """
                SELECT * FROM dialogs
                WHERE place_instance_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (place_instance_id, limit),
            ).fetchall()
        return self.conn.execute(
            """
            SELECT * FROM dialogs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def get_dialog(self, dialog_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM dialogs WHERE id = ?", (dialog_id,)
        ).fetchone()

    def find_dialog(
        self,
        query: str,
        *,
        place_instance_id: str | None = None,
    ) -> sqlite3.Row | None:
        """
        Resolve by slug, id, ordinal (1-based list order), or unique title.

        Ordinals prefer the place-scoped list (when place_instance_id is set)
        so ``dialogs show 1`` matches the first row of bare ``dialogs``.
        """
        q = query.strip()
        if not q:
            return None
        by_slug = self.get_dialog_by_slug(q)
        if by_slug:
            return by_slug
        by_id = self.get_dialog(q)
        if by_id:
            return by_id
        # dlg_ prefix partial (legacy)
        if q.startswith("dlg_") or q.lower().startswith("dlg"):
            row = self.conn.execute(
                "SELECT * FROM dialogs WHERE id = ? OR id LIKE ?",
                (q, f"%{q}%"),
            ).fetchone()
            if row:
                return row
        if q.isdigit():
            n = int(q)
            if place_instance_id:
                here_rows = self.list_dialogs(
                    200, place_instance_id=place_instance_id
                )
                if 1 <= n <= len(here_rows):
                    return here_rows[n - 1]
            all_rows = self.list_dialogs(200)
            if 1 <= n <= len(all_rows):
                return all_rows[n - 1]
            return None
        rows = self.list_dialogs(200)
        hits = [
            r
            for r in rows
            if names_match(q, r["title"] or "")
            or (r["title"] or "").casefold() == q.casefold()
            or names_match(q, self.dialog_slug_of(r))
        ]
        if len(hits) == 1:
            return hits[0]
        return None

    def set_dialog_when(self, dialog_id: str, when_label: str | None) -> sqlite3.Row:
        """Replace when_label on a completed dialog; returns updated row."""
        row = self.get_dialog(dialog_id)
        if row is None:
            raise ValueError(f"No dialog {dialog_id}")
        self.conn.execute(
            "UPDATE dialogs SET when_label = ? WHERE id = ?",
            (when_label, dialog_id),
        )
        self.conn.commit()
        updated = self.get_dialog(dialog_id)
        assert updated is not None
        return updated

    def set_dialog_title(
        self,
        dialog_id: str,
        title: str,
        *,
        allow_empty: bool = False,
    ) -> sqlite3.Row:
        """Replace title on a completed dialog; sync matching dialog lore notes."""
        row = self.get_dialog(dialog_id)
        if row is None:
            raise ValueError(f"No dialog {dialog_id}")
        new_title = (title or "").strip()
        if not new_title and not allow_empty:
            raise ValueError("Dialog title must not be empty")
        self.conn.execute(
            "UPDATE dialogs SET title = ? WHERE id = ?",
            (new_title, dialog_id),
        )
        # Lore notes written at /fin use title "Dialog · …" and cite transcript id
        display = new_title or "Untitled dialog"
        lore_title = f"Dialog · {display}"
        needle = f"Transcript id: {dialog_id}"
        self.conn.execute(
            """
            UPDATE lore_revisions
            SET title = ?
            WHERE author = 'dialog' AND body LIKE ?
            """,
            (lore_title, f"%{needle}%"),
        )
        self.conn.commit()
        updated = self.get_dialog(dialog_id)
        assert updated is not None
        return updated

    def last_dialog_for_person(self, person_instance_id: str) -> sqlite3.Row | None:
        """Most recent completed dialog where the person is either speaker."""
        return self.conn.execute(
            """
            SELECT * FROM dialogs
            WHERE speaker_a_id = ? OR speaker_b_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (person_instance_id, person_instance_id),
        ).fetchone()

    # ── Books (ordered pages on book-kind instances) ─────────────────────

    def _require_book(self, instance_id: str) -> InstanceView:
        """Folio (leaf-bearing); legacy kind ``book`` still accepted."""
        inst = self.get_instance(instance_id)
        if inst is None:
            raise ValueError(f"No instance {instance_id}")
        if (inst.ven_kind or "").lower() not in ("folio", "book"):
            raise ValueError(f"{inst.name} is a {inst.ven_kind}, not a folio")
        return inst

    def book_incomplete(self, book_instance_id: str) -> bool:
        self._require_book(book_instance_id)
        row = self.conn.execute(
            "SELECT state_json FROM instances WHERE id = ?",
            (book_instance_id,),
        ).fetchone()
        if not row:
            return False
        state = json.loads(row["state_json"] or "{}")
        return bool(state.get("incomplete", False))

    def set_book_incomplete(self, book_instance_id: str, incomplete: bool) -> None:
        self._require_book(book_instance_id)
        row = self.conn.execute(
            "SELECT state_json FROM instances WHERE id = ?",
            (book_instance_id,),
        ).fetchone()
        state = json.loads(row["state_json"] or "{}") if row else {}
        state["incomplete"] = bool(incomplete)
        self.conn.execute(
            "UPDATE instances SET state_json = ? WHERE id = ?",
            (json.dumps(state), book_instance_id),
        )
        self.conn.commit()

    def book_status(self, book_instance_id: str) -> str:
        """empty | incomplete | complete (empty when no pages — default for new books)."""
        from .book import resolve_book_status

        pages = self.list_book_pages(book_instance_id)
        return resolve_book_status(
            page_count=len(pages),
            incomplete=self.book_incomplete(book_instance_id),
        )

    def list_book_pages(self, book_instance_id: str) -> list[sqlite3.Row]:
        self._require_book(book_instance_id)
        return self.conn.execute(
            """
            SELECT * FROM book_pages
            WHERE book_instance_id = ?
            ORDER BY position ASC
            """,
            (book_instance_id,),
        ).fetchall()

    def _renumber_book_pages(self, book_instance_id: str) -> None:
        rows = self.conn.execute(
            """
            SELECT id FROM book_pages
            WHERE book_instance_id = ?
            ORDER BY position ASC, created_at ASC
            """,
            (book_instance_id,),
        ).fetchall()
        for i, r in enumerate(rows, start=1):
            self.conn.execute(
                "UPDATE book_pages SET position = ? WHERE id = ?",
                (i, r["id"]),
            )

    def add_book_page(
        self,
        book_instance_id: str,
        title: str,
        body: str,
        *,
        position: int | None = None,
    ) -> str:
        """
        Append a page (position=None) or insert at 1-based position.
        Existing pages at/after insert position shift up.
        """
        self._require_book(book_instance_id)
        pages = self.list_book_pages(book_instance_id)
        n = len(pages)
        if position is None:
            pos = n + 1
        else:
            if position < 1:
                raise ValueError("page position must be >= 1")
            pos = min(position, n + 1)
            # shift positions up to make room (work high→low to avoid UNIQUE clashes)
            for p in range(n, pos - 1, -1):
                self.conn.execute(
                    """
                    UPDATE book_pages SET position = position + 1
                    WHERE book_instance_id = ? AND position = ?
                    """,
                    (book_instance_id, p),
                )
        pid = new_id("page")
        self.conn.execute(
            """
            INSERT INTO book_pages(id, book_instance_id, position, title, body)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pid, book_instance_id, pos, title or "", body or ""),
        )
        self.conn.commit()
        return pid

    def get_book_page_at(self, book_instance_id: str, index: int) -> sqlite3.Row | None:
        """0-based index into ordered pages."""
        pages = self.list_book_pages(book_instance_id)
        if index < 0 or index >= len(pages):
            return None
        return pages[index]

    def _book_page_row(self, book_instance_id: str, page_position: int) -> sqlite3.Row:
        if page_position < 1:
            raise ValueError("page position must be >= 1")
        pages = self.list_book_pages(book_instance_id)
        if not pages:
            raise ValueError("book has no pages")
        if page_position > len(pages):
            raise ValueError(f"page position must be between 1 and {len(pages)}")
        return pages[page_position - 1]

    def _update_book_page_body(self, page_id: str, new_body: str) -> sqlite3.Row:
        self.conn.execute(
            "UPDATE book_pages SET body = ? WHERE id = ?",
            (new_body, page_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM book_pages WHERE id = ?",
            (page_id,),
        ).fetchone()
        assert row is not None
        return row

    def set_book_page_body(
        self,
        book_instance_id: str,
        page_position: int,
        body: str,
    ) -> sqlite3.Row:
        """Replace the full body of a 1-based page (e.g. studio rewrite)."""
        self._require_book(book_instance_id)
        page = self._book_page_row(book_instance_id, page_position)
        return self._update_book_page_body(page["id"], body if body is not None else "")

    def set_book_page_title(
        self,
        book_instance_id: str,
        page_position: int,
        title: str,
    ) -> sqlite3.Row:
        """Replace the title of a 1-based page (reader chrome / page heading)."""
        self._require_book(book_instance_id)
        page = self._book_page_row(book_instance_id, page_position)
        return self.set_book_page_title_by_id(page["id"], title)

    def set_book_page_title_by_id(self, page_id: str, title: str) -> sqlite3.Row:
        """Replace title by stable page id (safe across insert renumbering)."""
        self.conn.execute(
            "UPDATE book_pages SET title = ? WHERE id = ?",
            ((title or "").strip(), page_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM book_pages WHERE id = ?",
            (page_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No book page {page_id}")
        return row

    def set_book_page_body_by_id(self, page_id: str, body: str) -> sqlite3.Row:
        """Replace body by stable page id (safe across insert renumbering)."""
        return self._update_book_page_body(
            page_id, body if body is not None else ""
        )

    def insert_book_page_lines(
        self,
        book_instance_id: str,
        page_position: int,
        line_at: int,
        text: str,
    ) -> sqlite3.Row:
        """
        Amend new line/paragraph unit(s) into a page at 1-based line position.

        ``page_position`` is the page's 1-based order in the book.
        ``line_at`` is where the first new unit is placed (1 = start of page,
        len(lines)+1 = end). Multi-line text becomes multiple numbered units.
        Returns the updated page row.
        """
        from .book import insert_page_lines

        self._require_book(book_instance_id)
        page = self._book_page_row(book_instance_id, page_position)
        new_body = insert_page_lines(page["body"] or "", line_at, text)
        return self._update_book_page_body(page["id"], new_body)

    def remove_book_page_line(
        self,
        book_instance_id: str,
        page_position: int,
        line_no: int,
    ) -> sqlite3.Row:
        """Remove 1-based line unit from a page; renumbers remaining lines."""
        from .book import remove_page_line

        self._require_book(book_instance_id)
        page = self._book_page_row(book_instance_id, page_position)
        new_body = remove_page_line(page["body"] or "", line_no)
        return self._update_book_page_body(page["id"], new_body)

    def move_book_page_line(
        self,
        book_instance_id: str,
        page_position: int,
        from_line: int,
        to_line: int,
    ) -> sqlite3.Row:
        """Move a 1-based line unit to a new 1-based position on the same page."""
        from .book import move_page_line

        self._require_book(book_instance_id)
        page = self._book_page_row(book_instance_id, page_position)
        new_body = move_page_line(page["body"] or "", from_line, to_line)
        return self._update_book_page_body(page["id"], new_body)

    def get_book_line_text(
        self,
        book_instance_id: str,
        page_position: int,
        line_no: int,
    ) -> str:
        """Return the text of a 1-based line on a 1-based page (raises ValueError)."""
        from .book import split_page_lines

        page = self._book_page_row(book_instance_id, page_position)
        lines = split_page_lines(page["body"] or "")
        if line_no < 1 or line_no > len(lines):
            n = len(lines)
            raise ValueError(
                f"line position must be between 1 and {n}" if n else "page has no lines"
            )
        return lines[line_no - 1]

    def delete_book_page(self, book_instance_id: str, page_id: str) -> None:
        """Delete a page by id and renumber remaining pages contiguously."""
        self._require_book(book_instance_id)
        self.conn.execute(
            "DELETE FROM book_pages WHERE id = ? AND book_instance_id = ?",
            (page_id, book_instance_id),
        )
        self._renumber_book_pages(book_instance_id)
        self.conn.commit()

