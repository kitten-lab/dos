"""ID helpers and cute naming (ALL-CAPS, dash-separated)."""

from __future__ import annotations

import re
import uuid

# Canonical display/slug shape: SILVER-THREAD, PRIME, HALL-OF-SHELVED-YEARS
_CUTE_RE = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*$")

# Compact VEN code: 3-letter kind prefix + 3-digit seq (RLM-001, OBJ-014)
# Parse accepts 1–4 digits; canonical form is zero-padded to 3 when ≤999
_VEN_CODE_RE = re.compile(r"^([A-Z]{3})-(\d{1,4})$", re.IGNORECASE)
# Instance short ref built on a ven code: RLM-001-0001
_VEN_CODE_INST_RE = re.compile(
    r"^([A-Z]{3})-(\d{1,4})-(\d{1,4})$", re.IGNORECASE
)

# Kind → typeable 3-letter prefix (stable; used for VEN codes)
KIND_CODE_PREFIX: dict[str, str] = {
    "person": "PER",
    "place": "PLC",
    "bin": "BIN",
    "thing": "THG",
    "folio": "FOL",
    "symbol": "SYM",
    "sense": "SNS",
    "event": "EVT",
    "realm": "RLM",
    "timeline": "TLN",
    "ticket": "TKT",  # shared Ticket prime only; slips use TDF-… codes
    # legacy (read/compat; create folds these away)
    "container": "CTR",  # old store-root codes still parse
    "object": "OBJ",
    "book": "BOK",
    "material": "MAT",
    "concept": "CON",
    "feeling": "FEL",
    "goal": "GOL",
    "desire": "DES",
    "purpose": "PUR",
    "archetype": "ARC",
    "other": "OTH",
}


def kind_code_prefix(kind: str) -> str:
    """Three-letter prefix for a VEN kind."""
    return KIND_CODE_PREFIX.get((kind or "").lower().strip(), "OTH")


def format_ven_code(prefix: str, n: int) -> str:
    """XXX-NNN with zero-padded sequence."""
    p = (prefix or "OTH").strip().upper()[:3].ljust(3, "X")
    if n < 1:
        n = 1
    if n > 999:
        # Overflow: still valid shape, more digits after dash
        return f"{p}-{n}"
    return f"{p}-{n:03d}"


def normalize_ref_separators(raw: str | None) -> str:
    """
    Soft code typing: spaces / underscores act like dashes.

    ``bin 003 0043`` → ``BIN-003-0043``; ``BIN_003`` → ``BIN-003``.
    """
    if raw is None:
        return ""
    s = str(raw).strip().lstrip("#").upper()
    if not s:
        return ""
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def parse_ven_code(raw: str | None) -> str | None:
    """
    Normalize a typed VEN code to canonical XXX-NNN, or None if not a code.

    Accepts rlm-1, RLM-001, rlm001, ``bin 3``, ``BIN 003`` (spaces ok).
    """
    if raw is None:
        return None
    s = normalize_ref_separators(raw)
    if not s:
        return None
    m = _VEN_CODE_RE.fullmatch(s)
    if m:
        return format_ven_code(m.group(1), int(m.group(2)))
    # RLM001 without dash
    m2 = re.fullmatch(r"([A-Z]{3})(\d{1,4})", s)
    if m2:
        return format_ven_code(m2.group(1), int(m2.group(2)))
    return None


def parse_history_event_code(raw: str | None) -> str | None:
    """
    Normalize a history event code to HST-NNN, or None.

    Accepts hst-1, HST-001, hst001.
    """
    if raw is None:
        return None
    s = str(raw).strip().upper().replace("_", "-")
    if not s:
        return None
    m = re.fullmatch(r"HST-(\d{1,4})", s)
    if m:
        return format_ven_code("HST", int(m.group(1)))
    m2 = re.fullmatch(r"HST(\d{1,4})", s)
    if m2:
        return format_ven_code("HST", int(m2.group(1)))
    return None


def is_ven_code(raw: str | None) -> bool:
    return parse_ven_code(raw) is not None


# Temporary Data Fragment codes: TDF-48291037 (not VEN primes)
_TDF_CODE_RE = re.compile(r"^TDF-(\d{4,12})$", re.IGNORECASE)


def format_tdf_code(n: int) -> str:
    """TDF-NNNNNNNN (8 digits when possible)."""
    if n < 0:
        n = 0
    if n <= 99_999_999:
        return f"TDF-{n:08d}"
    return f"TDF-{n}"


def parse_tdf_code(raw: str | None) -> str | None:
    """Normalize TDF-… codes; accepts tdf-123, TDF 12345678."""
    if raw is None:
        return None
    s = normalize_ref_separators(raw)
    if not s:
        return None
    m = _TDF_CODE_RE.fullmatch(s)
    if m:
        return format_tdf_code(int(m.group(1)))
    m2 = re.fullmatch(r"TDF(\d{4,12})", s)
    if m2:
        return format_tdf_code(int(m2.group(1)))
    return None


def is_tdf_code(raw: str | None) -> bool:
    return parse_tdf_code(raw) is not None


def new_tdf_code() -> str:
    """Random TDF code for a printed slip (expand later for origin stamps)."""
    import secrets

    return format_tdf_code(secrets.randbelow(100_000_000))


def new_id(prefix: str = "") -> str:
    u = uuid.uuid4().hex[:12]
    return f"{prefix}_{u}" if prefix else u


def split_as_title(text: str) -> tuple[str, str] | None:
    """
    Split ``<left> as <title>`` or ``<left> -> <title>`` (also ``→``).

    Word ``as`` stays for sentence-style writing; arrow is the compact form.
    No flag form (``-a`` / ``--as``) — those are reserved for add elsewhere.
    Uses the rightmost separator. Returns (left, title) or None.
    """
    s = (text or "").strip()
    if not s:
        return None
    best = -1
    seplen = 0
    low = s.lower()
    i = low.rfind(" as ")
    if i >= 0:
        best, seplen = i, 4
    for sep in (" -> ", " → ", "->", "→"):
        j = s.rfind(sep)
        if j > best:
            best, seplen = j, len(sep)
    if best < 0:
        return None
    left = s[:best].strip()
    right = s[best + seplen :].strip()
    if left and right:
        return left, right
    return None


def cute_name(name: str) -> str:
    """Normalize human input into attractive ALL-CAPS dash form.

    Used for **VEN prime slugs** and for **matching** only — not for formal
    display names (see :func:`normalize_formal_name`).
    Instance display titles use :func:`normalize_instance_title` instead.

    Apostrophes and double-quotes are stripped (no dash gap) so
    ``Chester's`` → ``CHESTERS`` rather than ``CHESTER-S``.
    Other non-alphanumerics become dashes.

    Examples:
      "Silver Thread" -> "SILVER-THREAD"
      "prime" -> "PRIME"
      "Chester's" -> "CHESTERS"
      "Hall of Shelved Years (Shattered)" -> "HALL-OF-SHELVED-YEARS-SHATTERED"
    """
    if name is None:
        return "UNNAMED"
    s = str(name).strip().upper()
    # Strip quotes/apostrophes without inserting a separator (avoids Chester S)
    s = re.sub(r"['\"\u2018\u2019\u201c\u201d]+", "", s)
    s = re.sub(r"[^A-Z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s or "UNNAMED"


def normalize_formal_name(name: str | None) -> str:
    """
    Light normalize for **prime VEN formal names** (stored in ``vens.name``).

    Preserves user-intended casing and allows ``'``, ``"``, and ``-`` inside
    the name (e.g. ``Chester's``, ``Terminal IO``). Only collapses whitespace.
    Does **not** force ALL-CAPS cute form — that is the slug via :func:`cute_name`.
    """
    if name is None:
        return "Unnamed"
    s = str(name).strip()
    if not s:
        return "Unnamed"
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r" +", " ", s).strip()
    return s or "Unnamed"


def normalize_instance_title(name: str | None) -> str:
    """
    Light normalize for **instance** display titles (spawn as / rename).

    Preserves intentional CAPS and common separators (``-``, ``/``, ``.``, etc.)
    so book-like titles work: ``Terminal-Prolog``, ``Field Notes / Vol.1``.
    Collapses internal whitespace; does **not** force ALL-CAPS cute form.
    """
    if name is None:
        return "Unnamed"
    s = str(name).strip()
    if not s:
        return "Unnamed"
    # Normalize newlines/tabs to spaces; collapse runs of whitespace
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r" +", " ", s).strip()
    return s or "Unnamed"


def slugify(name: str) -> str:
    """Slug = cute name (same convention for primes and labels)."""
    return cute_name(name)


def is_cute_name(value: str) -> bool:
    return bool(value) and bool(_CUTE_RE.fullmatch(value))


def display_name(name: str | None) -> str:
    """Player-facing label for VEN formal names, cute slugs, or instance titles.

    Formal names (mixed case, apostrophes, etc.) are shown as stored.
    Legacy cute ALL-CAPS dash storage becomes title case with spaces.
    Examples:
      \"SILVER-THREAD\" -> \"Silver Thread\"
      \"Chester's\" -> \"Chester's\" (formal, unchanged)
      \"Terminal IO\" -> \"Terminal IO\" (formal CAPS preserved)
      \"Quiet Invitation\" -> \"Quiet Invitation\" (unchanged)
      \"Terminal-Prolog\" -> \"Terminal-Prolog\" (hyphen + CAPS preserved)
      \"Field Notes / Vol.1\" -> \"Field Notes / Vol.1\"
      \"PRIME\" -> \"Prime\" (legacy single-token cute)
    """
    if name is None:
        return ""
    s = str(name).strip()
    if not s:
        return ""
    # Formal / instance titles that are not pure cute form — keep as stored
    # (includes apostrophes, quotes, mixed case, spaces, etc.)
    if not is_cute_name(s):
        return s
    # Legacy cute ALL-CAPS dash (or single token) storage → title case
    parts = re.split(r"[-_]+", s)
    return " ".join(p[:1].upper() + p[1:].lower() if p else "" for p in parts if p)


def names_match(query: str, candidate: str) -> bool:
    """
    Name match without partial *word* hits.

    Matches when:
    - cute-form equal (``Silver Thread`` ↔ ``SILVER-THREAD``), or
    - casefold title equal, or
    - query is a **whole token** sequence in the candidate
      (``silver`` ↔ ``Silver Thread``; ``field notes`` ↔ slug FIELD-NOTES)

    Does **not** match substrings inside a token: ``q1`` does **not** hit
    ``Q1G1`` (Q1 is not a full token of Q1G1).
    """
    if not query or not candidate:
        return False
    q, c = query.strip(), candidate.strip()
    if not q:
        return False
    q_cute, c_cute = cute_name(q), cute_name(c)
    if q_cute == c_cute:
        return True
    if q.casefold() == c.casefold():
        return True
    q_tokens = [t for t in q_cute.split("-") if t]
    c_tokens = [t for t in c_cute.split("-") if t]
    if not q_tokens or not c_tokens:
        return False
    if len(q_tokens) == 1:
        return q_tokens[0] in c_tokens
    n, m = len(q_tokens), len(c_tokens)
    if n > m:
        return False
    for i in range(m - n + 1):
        if c_tokens[i : i + n] == q_tokens:
            return True
    return False


def format_instance_ref(n: int) -> str:
    """Zero-padded sequential part only: 1 → 0001 (stored / matched)."""
    if n < 1:
        n = 1
    return f"{n:04d}"


def format_instance_short_ref(
    slug: str,
    n: int | str,
    *,
    ven_code: str | None = None,
) -> str:
    """
    Player-facing short ref for an instance.

    Prefer compact VEN code: ``OBJ-014-0001``.
    Fallback (legacy): cute slug + digits ``FIELD-NOTES-0001``.
    """
    if isinstance(n, int):
        digits = format_instance_ref(n)
    else:
        s = str(n).strip()
        dig = digits_from_short_ref(s)
        digits = dig if dig else format_instance_ref(1)
    code = parse_ven_code(ven_code) if ven_code else None
    if code:
        return f"{code}-{digits}"
    base = cute_name(slug) if slug else "ITEM"
    return f"{base}-{digits}"


def digits_from_short_ref(raw: str | None) -> str | None:
    """Extract zero-padded digits from stored or composite short ref."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.isdigit():
        return format_instance_ref(int(s))
    m = re.search(r"(\d+)$", s)
    if m:
        return format_instance_ref(int(m.group(1)))
    return None


def parse_instance_ref_token(token: str) -> str | None:
    """
    Parse a short-ref token for resolve.

    Accepts:
      #0001 / 0001 / #1 → digit form ``0001``
      #FIELD-NOTES-0002 / FIELD-NOTES-0002 → composite ``FIELD-NOTES-0002``
      BIN-003-0043 / bin 003 0043 / BIN 3 43 → ``BIN-003-0043``
    """
    t = (token or "").strip()
    if t.startswith("#"):
        t = t[1:].strip()
    if not t:
        return None
    # Soft separators before digit-only check (multi-token codes)
    soft = normalize_ref_separators(t)
    if soft.isdigit():
        return format_instance_ref(int(soft))
    if t.isdigit():
        return format_instance_ref(int(t))
    # Compact VEN code + instance digits: XXX-NNN-NNNN
    m_code = re.fullmatch(r"([A-Z]{3})-(\d{1,4})-(\d{1,4})", soft)
    if m_code:
        return format_instance_short_ref(
            m_code.group(1),
            int(m_code.group(3)),
            ven_code=format_ven_code(m_code.group(1), int(m_code.group(2))),
        )
    # SLUG-…-NNNN (slug may contain hyphens) — use soft form
    m = re.fullmatch(r"(.+)-(\d+)$", soft)
    if m:
        slug_part, num = m.group(1), m.group(2)
        # Prefer VEN-code composite when left side is a code
        left_code = parse_ven_code(slug_part)
        if left_code:
            return format_instance_short_ref(
                left_code, int(num), ven_code=left_code
            )
        return format_instance_short_ref(slug_part, int(num))
    return None


def parse_resolve_query(query: str) -> tuple[str, str | None, str | None]:
    """
    Split a player name query into (base_name, where, short_ref).

    where: 'here' | 'inv' | None
    short_ref: digit ``0001`` and/or composite ``FIELD-NOTES-0001`` / ``BIN-003-0043``

    Soft codes: spaces/underscores count as dashes
    (``bin 003 0043`` → instance ref ``BIN-003-0043``).

    Examples:
      field-notes inv
      field-notes#0002
      FIELD-NOTES-0002
      bin 003 0043
      BIN-003-0043
      Pocket Notes
    """
    raw = query.strip()
    if not raw:
        return "", None, None
    where: str | None = None
    ref: str | None = None

    # Pull trailing where qualifier first
    tokens = raw.split()
    loc_words = {"here", "inv", "inventory", "carried", "pack"}
    if tokens and tokens[-1].lower() in loc_words:
        w = tokens[-1].lower()
        where = "inv" if w in ("inv", "inventory", "carried", "pack") else "here"
        tokens = tokens[:-1]
        raw = " ".join(tokens).strip()

    if not raw:
        return "", where, None

    soft = normalize_ref_separators(raw)
    # Whole query is compact instance code: XXX-NNN-NNNN (spaces ok in input)
    if re.fullmatch(r"[A-Z]{3}-\d{1,4}-\d{1,4}", soft):
        maybe = parse_instance_ref_token(soft)
        if maybe:
            return "", where, maybe

    # Whole query is single-token composite short ref (slug or dashed form)
    if " " not in raw.strip():
        maybe = parse_instance_ref_token(raw)
        if maybe and ("-" in raw or raw.lstrip("#").isdigit()):
            return "", where, maybe

    # Embedded or trailing #ref
    if "#" in raw:
        left, right = raw.rsplit("#", 1)
        maybe = parse_instance_ref_token(right.strip())
        if maybe:
            ref = maybe
            raw = left.strip()
    else:
        tokens = raw.split()
        if tokens:
            maybe = parse_instance_ref_token(tokens[-1])
            tok = tokens[-1].lstrip("#")
            # pure digits only as trailing ref when multi-token (not bare "2024")
            if maybe and tok.isdigit() and len(tokens) > 1:
                ref = maybe
                raw = " ".join(tokens[:-1]).strip()

    return raw, where, ref
