"""Small text helpers for builder input."""

from __future__ import annotations


def escape_desc(s: str) -> str:
    """
    Encode real newlines/backslashes for a one-line dispatch command.

    Inverse of :func:`unescape_desc`. Multiline collectors join lines with real
    ``\\n``; book page parsers tokenize with ``str.split()``, which would
    collapse those breaks to spaces. Escape first so store sees logical lines.
    """
    if not s:
        return s
    # Backslashes first so existing ``\\n`` literals round-trip correctly.
    return (
        s.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
    )


def unescape_desc(s: str) -> str:
    """Turn typed escapes into real characters: ``\\n`` → newline, ``\\\\`` → ``\\``."""
    if not s:
        return s
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
        out.append(s[i])
        i += 1
    return "".join(out)
