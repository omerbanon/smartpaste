"""Clipboard history for SmartPaste.

Keeps the last N text copies, newest first, in memory. Nothing is saved
unless the user turns on "Keep History After Quit"; then HistoryStore keeps
a copy in the macOS Keychain (encrypted at rest).
ClipboardWatcher polls the pasteboard change counter and feeds the history.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

CAPACITY = 15


@dataclass
class HistoryItem:
    text: str
    copied_at: float


class ClipboardHistory:
    def __init__(self, capacity: int = CAPACITY, on_change: Callable[["ClipboardHistory"], None] | None = None):
        self._capacity = max(1, capacity)
        self._items: list[HistoryItem] = []
        self.on_change = on_change

    @property
    def capacity(self) -> int:
        return self._capacity

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change(self)
            except Exception:
                log.exception("History change handler failed")

    def clear(self) -> None:
        self._items = []
        self._changed()

    def load(self, items: list[HistoryItem]) -> None:
        """Replace the contents (newest first), trimmed to capacity. Doesn't fire on_change."""
        self._items = [i for i in items if i.text and i.text.strip()][: self._capacity]

    def push(self, text: str, now: float | None = None) -> bool:
        """Record *text* at the top. Returns False if it was skipped."""
        if not text or not text.strip():
            return False
        now = time.time() if now is None else now
        self._items = [i for i in self._items if i.text != text]
        self._items.insert(0, HistoryItem(text, now))
        del self._items[self._capacity:]
        self._changed()
        return True

    def items(self) -> list[HistoryItem]:
        return list(self._items)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self._changed()

    def touch(self, index: int) -> None:
        """Move the item at *index* to the top (it was just re-used)."""
        if 0 <= index < len(self._items):
            self._items.insert(0, self._items.pop(index))
            self._changed()

    def __len__(self) -> int:
        return len(self._items)


# Upper bound for what's kept across restarts; oldest items are dropped first.
MAX_SAVED_BYTES = 1_000_000


def dump_items(items: list[HistoryItem], max_bytes: int = MAX_SAVED_BYTES) -> str:
    """Serialize history (newest first), dropping the oldest items past *max_bytes*."""
    kept: list[dict] = []
    size = 0
    for item in items:
        size += len(item.text.encode("utf-8")) + 40
        if size > max_bytes:
            break
        kept.append({"text": item.text, "copied_at": item.copied_at})
    return json.dumps({"version": 1, "items": kept}, ensure_ascii=False)


def parse_items(raw: str | None) -> list[HistoryItem]:
    """Inverse of dump_items(); returns [] for missing or damaged data."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [HistoryItem(str(i["text"]), float(i["copied_at"])) for i in data.get("items", [])]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        log.warning("Ignoring unreadable saved history: %s", exc)
        return []


class HistoryStore:
    """Saves history to the Keychain. Used only when "keep_history" is on."""

    def __init__(self, get=None, put=None, delete=None):
        from smartpaste import keychain

        account = keychain.HISTORY_ACCOUNT
        self._get = get or (lambda: keychain.get_secret(account))
        self._put = put or (lambda raw: keychain.set_secret(raw, account))
        self._delete = delete or (lambda: keychain.delete_secret(account))

    def load(self) -> list[HistoryItem]:
        return parse_items(self._get())

    def save(self, history: ClipboardHistory) -> None:
        if not self._put(dump_items(history.items())):
            log.warning("Could not save clipboard history to the Keychain")

    def delete(self) -> None:
        self._delete()


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

    def _tick(self, _timer) -> None:
        """Timer callback. Must return None: a repeating NSTimer block that
        returns a value fires once and then silently stops."""
        try:
            self.poll()
        except Exception:
            log.exception("Clipboard poll failed")

    def start(self, interval: float = 0.5) -> None:
        """Poll on the main run loop every *interval* seconds."""
        from AppKit import NSTimer
        self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            interval, True, self._tick
        )
