"""Session-only undo stack for the last builder mutations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World


@dataclass
class UndoEntry:
    summary: str
    apply: Callable[["World"], None]


class UndoStack:
    def __init__(self, max_entries: int = 50) -> None:
        self._items: list[UndoEntry] = []
        self._max = max_entries

    def __len__(self) -> int:
        return len(self._items)

    def push(self, summary: str, apply: Callable[["World"], None]) -> None:
        self._items.append(UndoEntry(summary=summary, apply=apply))
        if len(self._items) > self._max:
            self._items = self._items[-self._max :]

    def undo(self, world: "World") -> str:
        """Pop and apply the last inverse. Returns summary of what was undone."""
        if not self._items:
            raise ValueError("Nothing to undo")
        entry = self._items.pop()
        entry.apply(world)
        return entry.summary
