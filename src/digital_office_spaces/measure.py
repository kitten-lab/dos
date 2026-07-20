"""Canonical content measure for Digital Office Spaces.

Authors should compose look-critical text (books, studio layout, rules) as if
the content column is this many characters wide. Side rails and OS chrome are
secondary; they must not redefine the artboard.
"""

from __future__ import annotations

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


def wrap_text_hanging(text: str, content_width: int) -> list[str]:
    """
    Hard-wrap one logical line into segments of at most *content_width*.

    Prefers breaking on spaces; long tokens are split. Empty → ``[""]``.
    Used by book gutters and studio field-row hang wraps.
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
    parts: list[str] = []
    remaining = s
    while remaining:
        if len(remaining) <= content_width:
            parts.append(remaining)
            break
        chunk = remaining[:content_width]
        sp = chunk.rfind(" ")
        # Prefer word break if not too early in the segment
        if sp >= max(1, content_width // 4):
            parts.append(remaining[:sp])
            remaining = remaining[sp + 1 :]
        else:
            parts.append(chunk)
            remaining = remaining[content_width:]
    return parts or [""]
