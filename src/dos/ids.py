"""ID helpers and cute naming (ALL-CAPS, dash-separated)."""

from __future__ import annotations

import re
import uuid

# Canonical display/slug shape: SILVER-THREAD, PRIME, HALL-OF-SHELVED-YEARS
_CUTE_RE = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*$")

# Legacy compact VEN code: 3-letter kind prefix + 3-digit seq (RLM-001, OBJ-014)
_VEN_CODE_LEGACY_RE = re.compile(r"^([A-Z]{3})-(\d{1,4})$", re.IGNORECASE)
_VEN_CODE_RE = _VEN_CODE_LEGACY_RE  # alias for older imports
# Instance short ref built on a legacy ven code: RLM-001-0001
_VEN_CODE_INST_RE = re.compile(
    r"^([A-Z]{3})-(\d{1,4})-(\d{1,4})$", re.IGNORECASE
)
# DOS office face codes: 3 from cute-slug + hex entropy (com-7f3a2c)
# Optional instance trailer: com-7f3a2c.2  (no .1 — bare is first/only)
_OFFICE_VEN_CODE_RE = re.compile(
    r"^([a-z0-9]{2,4})-([0-9a-f]{4,12})(?:\.(\d+))?$",
    re.IGNORECASE,
)
_OFFICE_HEX_LEN = 6  # token_hex(3)

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
    """Legacy XXX-NNN with zero-padded sequence (history HST, old worlds)."""
    p = (prefix or "OTH").strip().upper()[:3].ljust(3, "X")
    if n < 1:
        n = 1
    if n > 999:
        return f"{p}-{n}"
    return f"{p}-{n:03d}"


# Office face prefixes we refuse (accidental rude reads from first-3-of-name).
# Keep short; only block the face *prefix*, not full names.
_FACE_PREFIX_BLOCKLIST = frozenset(
    {
        "ass",
        "azz",
        "sex",
        "fag",
        "fuk",
        "fuc",
        "cum",
        "tit",
        "dic",
        "dik",
        "coc",
        "cok",
        "nig",
        "nob",
        "pis",
        "shi",
        "std",
        "kkk",
        "gay",
        "jew",  # jewelry etc. — skip the accidental face
        "rap",
        "cnt",
        "fgt",
    }
)


def _normalize_face_prefix(raw: str) -> str:
    """Lowercase alnum face prefix, pad/truncate to 3."""
    letters = re.sub(r"[^a-z0-9]", "", (raw or "").lower())
    if not letters:
        letters = "xxx"
    if len(letters) < 3:
        letters = (letters + "xxx")[:3]
    return letters[:3]


def slug_face_prefix(slug_or_name: str) -> str:
    """
    3-char office face prefix from the cute-slug (lowercase).

    Prefers the first token's leading letters (``Company Handbook`` → ``com``).
    Multi-word blends kick in when that would be unfortunate or too short
    (``Assigned Leads`` → ``asl``, not ``ass``).

    Pads with ``x`` if shorter than 3. Avoids a small blocklist of rude reads.
    """
    cute = cute_name(slug_or_name or "")
    tokens = [
        re.sub(r"[^A-Z0-9]", "", t) for t in cute.split("-") if t
    ]
    tokens = [t for t in tokens if t]
    letters = "".join(tokens) if tokens else re.sub(r"[^A-Z0-9]", "", cute)

    candidates: list[str] = []
    if tokens:
        t0 = tokens[0]
        # Usual case: first 3 of first word (com from company)
        if len(t0) >= 3:
            candidates.append(t0[:3])
        elif t0:
            candidates.append(t0)
        if len(tokens) >= 2:
            t1 = tokens[1]
            # Assigned Leads → asl / ale (not ass)
            candidates.append((t0[:2] + t1[:1])[:3])
            candidates.append((t0[:1] + t1[:2])[:3])
            ini = "".join(t[0] for t in tokens[:3])
            candidates.append(ini)
        if len(tokens) >= 3:
            candidates.append(
                (tokens[0][:1] + tokens[1][:1] + tokens[2][:1])[:3]
            )
    if letters:
        candidates.append(letters[:3])
        # slide window / consonants as soft fallbacks
        if len(letters) > 3:
            candidates.append(letters[1:4])
        cons = re.sub(r"[AEIOU]", "", letters)
        if len(cons) >= 3:
            candidates.append(cons[:3])

    seen: set[str] = set()
    for raw in candidates:
        pref = _normalize_face_prefix(raw)
        if pref in seen:
            continue
        seen.add(pref)
        if pref not in _FACE_PREFIX_BLOCKLIST:
            return pref

    # Last resort: never emit a blocked prefix
    base = _normalize_face_prefix(letters or "xxx")
    if base not in _FACE_PREFIX_BLOCKLIST:
        return base
    return "x" + base[:2]


def mint_office_ven_code(
    slug_or_name: str,
    *,
    taken: set[str] | None = None,
) -> str:
    """
    DOS face code: ``{slug3}-{hex6}`` lowercase, e.g. ``com-7f3a2c``.

    Entropy only — no genesis ordinal. *taken* is lowercased codes in use.
    """
    import secrets

    prefix = slug_face_prefix(slug_or_name)
    used = {t.lower() for t in (taken or set())}
    for _ in range(64):
        ent = secrets.token_hex(_OFFICE_HEX_LEN // 2)
        code = f"{prefix}-{ent}"
        if code not in used:
            return code
    # Extremely unlikely
    return f"{prefix}-{secrets.token_hex(4)}"


def is_office_ven_code(raw: str | None) -> bool:
    """True if *raw* is a DOS office face code (not legacy RLM-001)."""
    if raw is None:
        return False
    s = str(raw).strip().lstrip("#").lower()
    m = _OFFICE_VEN_CODE_RE.fullmatch(s)
    if not m:
        return False
    # Exclude pure legacy if somehow matched — legacy is LETTER-digits only
    return bool(re.fullmatch(r"[0-9a-f]+", m.group(2)))


def normalize_ref_separators(raw: str | None) -> str:
    """
    Soft code typing: spaces / underscores act like dashes.

    Legacy: ``bin 003 0043`` → ``BIN-003-0043`` (upper).
    Office codes are lowercased by :func:`parse_ven_code`.
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
    Normalize a typed VEN code, or None if not a code.

    **DOS office:** ``com-7f3a2c`` / ``COM-7F3A2C`` → ``com-7f3a2c``
    (optional ``.2`` trailer stripped for prime match).

    **Legacy:** ``rlm-1``, ``RLM-001``, ``bin 3`` → ``RLM-001`` / ``BIN-003``.
    """
    if raw is None:
        return None
    raw_s = str(raw).strip().lstrip("#")
    if not raw_s:
        return None
    # Office face (lowercase canonical); strip instance .N for prime code
    low = raw_s.lower().replace("_", "-")
    low = re.sub(r"\s+", "-", low)
    low = re.sub(r"-+", "-", low).strip("-")
    m_off = _OFFICE_VEN_CODE_RE.fullmatch(low)
    if m_off and re.fullmatch(r"[0-9a-f]+", m_off.group(2)):
        return f"{m_off.group(1)}-{m_off.group(2)}"
    # Bare office prime without instance: already handled; try without .N
    if "." in low:
        base = low.split(".", 1)[0]
        m2 = re.fullmatch(r"([a-z0-9]{2,4})-([0-9a-f]{4,12})", base)
        if m2:
            return f"{m2.group(1)}-{m2.group(2)}"
    # Legacy uppercase path
    s = normalize_ref_separators(raw)
    if not s:
        return None
    m = _VEN_CODE_LEGACY_RE.fullmatch(s)
    if m:
        return format_ven_code(m.group(1), int(m.group(2)))
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
    """Zero-padded sequential part only (storage): 1 → 0001."""
    if n < 1:
        n = 1
    return f"{n:04d}"


def instance_copy_number(n: int | str) -> int:
    """Integer copy index from stored short_ref digits or int."""
    if isinstance(n, int):
        return max(1, n)
    dig = digits_from_short_ref(str(n))
    if dig:
        return max(1, int(dig))
    return 1


def format_instance_short_ref(
    slug: str,
    n: int | str,
    *,
    ven_code: str | None = None,
    singleton: bool = False,
) -> str:
    """
    Player-facing short ref for an instance.

    **DOS office codes** (``com-7f3a2c``):
      - singleton or copy 1 → bare ``com-7f3a2c`` (no ``.1``)
      - copy 2+ → ``com-7f3a2c.2``

    **Legacy** (``OBJ-014``):
      - ``OBJ-014-0001`` (old dash + zero-pad)

    Fallback: cute slug + digits ``FIELD-NOTES-0001``.
    """
    num = instance_copy_number(n)
    digits = format_instance_ref(num)
    code = parse_ven_code(ven_code) if ven_code else None
    if not code and ven_code:
        code = str(ven_code).strip()
    if code and is_office_ven_code(code):
        face = code.lower()
        if singleton or num <= 1:
            return face
        return f"{face}.{num}"
    if code:
        # Legacy kind-serial
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
    # Office trailer: com-7f3a2c.2  (bare office prime is copy 1 — no digits)
    m_dot = re.search(r"\.(\d+)$", s)
    if m_dot:
        return format_instance_ref(int(m_dot.group(1)))
    base = s.split(".", 1)[0]
    if is_office_ven_code(base) or re.fullmatch(
        r"[a-z0-9]{2,4}-[0-9a-f]{4,12}", base, re.IGNORECASE
    ):
        return None
    # Legacy FOO-0001 / BIN-003-0001
    m = re.search(r"-(\d{1,4})$", s)
    if m:
        return format_instance_ref(int(m.group(1)))
    return None


def parse_instance_ref_token(token: str) -> str | None:
    """
    Parse a short-ref token for resolve.

    Accepts:
      #0001 / 0001 / #1 → digit form ``0001``
      com-7f3a2c / com-7f3a2c.2 → office face (canonical lower)
      #FIELD-NOTES-0002 / FIELD-NOTES-0002 → composite
      BIN-003-0043 / bin 003 0043 → legacy ``BIN-003-0043``
    """
    t = (token or "").strip()
    if t.startswith("#"):
        t = t[1:].strip()
    if not t:
        return None
    # Office face first (lowercase path; allows .2)
    low = t.lower().replace("_", "-")
    low = re.sub(r"\s+", "-", low)
    low = re.sub(r"-+", "-", low).strip("-")
    m_off = _OFFICE_VEN_CODE_RE.fullmatch(low)
    if m_off and re.fullmatch(r"[0-9a-f]+", m_off.group(2)):
        prime = f"{m_off.group(1)}-{m_off.group(2)}"
        if m_off.group(3):
            return format_instance_short_ref(
                prime, int(m_off.group(3)), ven_code=prime
            )
        return prime
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
