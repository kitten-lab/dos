"""Named flags for create/spawn (free order): --type --name --desc --when …"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from .story_when import normalize_story_when

# Long and short names → canonical key
_FLAG_ALIASES: dict[str, str] = {
    "type": "type",
    "kind": "type",
    "t": "type",
    "name": "name",
    "n": "name",
    "desc": "desc",
    "description": "desc",
    "d": "desc",
    "body": "body",
    "b": "body",
    "when": "when",
    "w": "when",
    "of": "of",
    "parent": "of",
    # Title for create/spawn maps to name; lore also reads name as title.
    "title": "name",
    "ven": "ven",
    "prime": "ven",
    "from": "ven",
    # -a / --add = insert into collection (lore, leaf later). No value required.
    "add": "add",
    "a": "add",
    # lore target: --on cartographer
    "on": "on",
}

# Presence-only flags (no value; stored as "1")
_BOOLEAN_FLAGS = frozenset({"add"})


@dataclass
class NamedFlags:
    """Parsed free-order flags + leftover positionals."""

    flags: dict[str, str] = field(default_factory=dict)
    positionals: list[str] = field(default_factory=list)
    error: str | None = None

    def get(self, key: str, default: str = "") -> str:
        return (self.flags.get(key) or default).strip()


_FLAG_START = re.compile(r"(^|\s)--?[A-Za-z]")


def looks_like_flag_command(text: str) -> bool:
    """True if the user used --type / -n style markers."""
    return bool(_FLAG_START.search(text or ""))


# @desc commit: optional -t/--title for lore title (not create's type)
DESC_COMMIT_FLAG_ALIASES: dict[str, str] = {
    "title": "name",
    "t": "name",
    "name": "name",
    "n": "name",
    "on": "on",
    "when": "when",
    "w": "when",
}

# Lore create: -t is title (not create's type); -d/-b body; -a add
LORE_FLAG_ALIASES: dict[str, str] = {
    "add": "add",
    "a": "add",
    "title": "name",
    "t": "name",
    "name": "name",
    "n": "name",
    "body": "body",
    "b": "body",
    "desc": "body",
    "description": "body",
    "d": "body",
    "when": "when",
    "w": "when",
    "on": "on",
}


def parse_named_flags(
    text: str,
    *,
    aliases: dict[str, str] | None = None,
    boolean_flags: frozenset[str] | None = None,
) -> NamedFlags:
    """
    Parse ``--key value``, ``--key=value``, ``-k value`` (single-letter).

    Values may be quoted. Order of flags does not matter.
    *aliases* overrides the default create/spawn map (e.g. lore uses
    :data:`LORE_FLAG_ALIASES` so ``-t`` is title not type).
    """
    table = aliases if aliases is not None else _FLAG_ALIASES
    bools = boolean_flags if boolean_flags is not None else _BOOLEAN_FLAGS
    raw = (text or "").strip()
    if not raw:
        return NamedFlags()
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError as e:
        return NamedFlags(error=f"Could not parse flags: {e}")

    def take_value(start: int) -> tuple[str, int]:
        """Value runs until next flag token (so multi-word titles work)."""
        if start >= len(tokens):
            return "", start
        parts: list[str] = []
        j = start
        while j < len(tokens) and not tokens[j].startswith("-"):
            parts.append(tokens[j])
            j += 1
        return " ".join(parts), j

    flags: dict[str, str] = {}
    positionals: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            body = tok[2:]
            if not body:
                return NamedFlags(error="Empty flag --")
            if "=" in body:
                key, _, val = body.partition("=")
                canon = table.get(key.lower())
                if not canon:
                    return NamedFlags(error=f"Unknown flag --{key}")
                flags[canon] = val
                i += 1
                continue
            canon = table.get(body.lower())
            if not canon:
                return NamedFlags(error=f"Unknown flag --{body}")
            if i + 1 >= len(tokens) or tokens[i + 1].startswith("-"):
                if canon in bools:
                    flags[canon] = "1"
                    i += 1
                    continue
                return NamedFlags(error=f"Flag --{body} needs a value")
            val, i = take_value(i + 1)
            flags[canon] = val
            continue
        if tok.startswith("-") and len(tok) >= 2 and tok[1].isalpha():
            letters = tok[1:]
            if len(letters) == 1:
                canon = table.get(letters.lower())
                if not canon:
                    return NamedFlags(error=f"Unknown flag -{letters}")
                if i + 1 >= len(tokens) or tokens[i + 1].startswith("-"):
                    if canon in bools:
                        flags[canon] = "1"
                        i += 1
                        continue
                    return NamedFlags(error=f"Flag -{letters} needs a value")
                val, i = take_value(i + 1)
                flags[canon] = val
                continue
            return NamedFlags(
                error=f"Use long flags or single -x (got {tok!r})"
            )
        positionals.append(tok)
        i += 1
    return NamedFlags(flags=flags, positionals=positionals)


def story_when_from_flag(raw: str | None) -> tuple[str, int | None]:
    """
    Normalize ``--when`` values: ``0``, ``@0``, ``unknown``, ``@unknown``.
    """
    s = (raw or "").strip()
    if not s:
        return "@unknown", None
    if s.isdigit():
        return f"@{int(s)}", int(s)
    if s.lower() in ("unknown", "@unknown"):
        return "@unknown", None
    if s.startswith("@"):
        return normalize_story_when(s)
    # freeform not a node
    return normalize_story_when(s)
