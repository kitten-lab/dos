"""Canonical content measure for Digital Office Spaces.

Authors should compose look-critical text (books, studio layout, rules) as if
the content column is this many characters wide. Side rails and OS chrome are
secondary; they must not redefine the artboard.
"""

from __future__ import annotations

import re

# Design measure for prose, book pages, turn HRs, and <<studio wrap guides.
CONTENT_MEASURE = 72


def measure_ruler(width: int = CONTENT_MEASURE) -> str:
    """
    Classic column ruler for the studio editor (ASCII, no Rich markup).

    Example (first 20): ``....+....1....+....2``
    """
    if width < 1:
        return ""
    chars: list[str] = []
    for i in range(1, width + 1):
        if i % 10 == 0:
            chars.append(str((i // 10) % 10))
        elif i % 5 == 0:
            chars.append("+")
        else:
            chars.append(".")
    return "".join(chars)


def turn_rule_ascii(width: int = CONTENT_MEASURE) -> str:
    """Plain ASCII horizontal rule of *width* dashes."""
    return "-" * max(1, width)


# Spans that must not be split mid-token when hang-wrapping book/studio lines
# (otherwise markdown links / bare URLs break before Studio Text renders them).
_WRAP_PROTECT_RE = re.compile(
    r"`[^`\n]+`"  # code
    r"|\[\[[^\]]+\]\]"  # wiki
    r"|\[[^\]]+\]\(https?://[^)\s]+\)"  # [label](https://…)
    r"|(?<![\w/@])https?://[^\s\[\]<>\"']+"  # bare URL
    r"|\{[a-zA-Z][\w-]*\}[^\n{]+?\{/(?:[a-zA-Z][\w-]*)?\}"  # {color}…{/}
)


def _wrap_tokens(text: str) -> list[str]:
    """
    Tokenize *text* into protected spans and space-separated words.

    Protected spans stay atomic (links, code, wiki, color). Spaces between
    tokens are not included — packer re-joins with single spaces.
    """
    s = str(text)
    if not s:
        return []
    tokens: list[str] = []
    pos = 0
    for m in _WRAP_PROTECT_RE.finditer(s):
        if m.start() > pos:
            for w in s[pos : m.start()].split(" "):
                if w:
                    tokens.append(w)
        tokens.append(m.group(0))
        pos = m.end()
    if pos < len(s):
        for w in s[pos:].split(" "):
            if w:
                tokens.append(w)
    return tokens


def wrap_text_hanging(text: str, content_width: int) -> list[str]:
    """
    Hard-wrap one logical line into segments of at most *content_width*.

    Prefers breaking on spaces; long tokens are split **except** protected
    spans (markdown links, bare URLs, wiki, code, color) which stay whole so
    the book viewer does not break ``[label](https://…)`` across lines.

    Empty → ``[""]``. Used by book gutters and studio field-row hang wraps.
    """
    if content_width < 1:
        content_width = 1
    if text is None:
        return [""]
    s = str(text)
    if not s:
        return [""]
    if len(s) <= content_width:
        return [s]

    tokens = _wrap_tokens(s)
    if not tokens:
        return [""]

    parts: list[str] = []
    line = ""

    def flush() -> None:
        nonlocal line
        if line:
            parts.append(line)
            line = ""

    for tok in tokens:
        # Protected or short: keep atomic if possible
        protected = bool(_WRAP_PROTECT_RE.fullmatch(tok))
        if not line:
            if len(tok) <= content_width or protected:
                # Overlong protected link: own line (do not mid-split)
                line = tok
                if len(tok) > content_width:
                    flush()
                continue
            # Overlong plain token — hard-split
            remaining = tok
            while len(remaining) > content_width:
                parts.append(remaining[:content_width])
                remaining = remaining[content_width:]
            line = remaining
            continue

        # Try to append with a space
        candidate = f"{line} {tok}"
        if len(candidate) <= content_width:
            line = candidate
            continue
        # Need new line
        flush()
        if len(tok) <= content_width or protected:
            line = tok
            if len(tok) > content_width:
                flush()
        else:
            remaining = tok
            while len(remaining) > content_width:
                parts.append(remaining[:content_width])
                remaining = remaining[content_width:]
            line = remaining
    flush()
    return parts or [""]
