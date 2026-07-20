"""Command-line input history (up/down through previous commands)."""

from __future__ import annotations


class CommandHistory:
    """In-memory command history with draft preservation while browsing."""

    def __init__(self, max_entries: int = 500) -> None:
        self._items: list[str] = []
        self._max = max_entries
        self._pos: int = 0  # index into _items; len(_items) means "new draft"
        self._draft: str = ""

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> list[str]:
        """Snapshot of stored lines (oldest first)."""
        return list(self._items)

    def push(self, line: str) -> None:
        line = line.strip()
        if not line:
            self._pos = len(self._items)
            self._draft = ""
            return
        if not self._items or self._items[-1] != line:
            self._items.append(line)
            if len(self._items) > self._max:
                self._items = self._items[-self._max :]
        self._pos = len(self._items)
        self._draft = ""

    def push_content_line(self, line: str) -> None:
        """
        Record one accepted multiline content line for up/down recall.

        Used by @desc << / <<studio and book page << / <<studio collection so
        studio work is not only an opener/summary stub.
        """
        self.push(line)

    def up(self, current: str) -> str | None:
        """Move older; returns text to show, or None if no change."""
        if not self._items:
            return None
        if self._pos == len(self._items):
            self._draft = current
        if self._pos <= 0:
            return self._items[0] if self._items else None
        self._pos -= 1
        return self._items[self._pos]

    def down(self, current: str) -> str | None:
        """Move newer; returns text to show, or None if no change."""
        if not self._items and not self._draft:
            return None
        if self._pos >= len(self._items):
            return None
        self._pos += 1
        if self._pos >= len(self._items):
            self._pos = len(self._items)
            return self._draft
        return self._items[self._pos]
