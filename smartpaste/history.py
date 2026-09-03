"""In-memory clipboard history for SmartPaste.

Keeps the last N text copies, newest first. Nothing is written to disk.
ClipboardWatcher polls the pasteboard change counter and feeds the history.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

CAPACITY = 15


@dataclass
class HistoryItem:
    text: str
    copied_at: float


class ClipboardHistory:
    def __init__(self, capacity: int = CAPACITY):
        self._capacity = capacity
        self._items: list[HistoryItem] = []

    @property
    def capacity(self) -> int:
        return self._capacity

    def push(self, text: str, now: float | None = None) -> bool:
        """Record *text* at the top. Returns False if it was skipped."""
        if not text or not text.strip():
            return False
        now = time.time() if now is None else now
        self._items = [i for i in self._items if i.text != text]
        self._items.insert(0, HistoryItem(text, now))
        del self._items[self._capacity:]
        return True

    def items(self) -> list[HistoryItem]:
        return list(self._items)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]

    def touch(self, index: int) -> None:
        """Move the item at *index* to the top (it was just re-used)."""
        if 0 <= index < len(self._items):
            self._items.insert(0, self._items.pop(index))

    def __len__(self) -> int:
        return len(self._items)


def age_label(copied_at: float, now: float | None = None) -> str:
    now = time.time() if now is None else now
    secs = max(0, int(now - copied_at))
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"


CONCEALED_TYPES = ("org.nspasteboard.ConcealedType", "org.nspasteboard.TransientType")


class ClipboardWatcher:
    """Polls the pasteboard change counter and records new text copies.

    All pasteboard access is injected so the rules are testable without AppKit.
    """

    def __init__(
        self,
        history: ClipboardHistory,
        *,
        change_count: Callable[[], int] | None = None,
        own_change_count: Callable[[], int] | None = None,
        read_types: Callable[[], list[str]] | None = None,
        read_text: Callable[[], str | None] | None = None,
    ):
        from smartpaste import clipboard as cb
        self._history = history
        self._change_count = change_count or cb.change_count
        self._own_change_count = own_change_count or cb.last_own_change_count
        self._read_types = read_types or cb.read_clipboard_types
        self._read_text = read_text or cb.read_clipboard_string
        self._last_seen = self._change_count()
        self._timer = None

    def poll(self) -> bool:
        """Check once. Returns True if a new item was recorded."""
        count = self._change_count()
        if count == self._last_seen:
            return False
        self._last_seen = count
        if count == self._own_change_count():
            return False
        if any(t in CONCEALED_TYPES for t in self._read_types()):
            return False
        text = self._read_text()
        if not text:
            return False
        return self._history.push(text)

    def start(self, interval: float = 0.5) -> None:
        """Poll on the main run loop every *interval* seconds."""
        from AppKit import NSTimer
        self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            interval, True, lambda _: self.poll()
        )
