# Clipboard History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remember the last 15 text copies and let the user pick one from the popup (key L) as the text the app works on.

**Architecture:** A main-thread timer polls the pasteboard change counter and pushes new text into an in-memory ring buffer (`history.py`). A separate `HistoryPanel` (`history_panel.py`, modeled on `PreviewPanel`) lists the items; the format popup dismisses itself and hands over to it on L, and the app re-shows the popup for whatever item is picked. `clipboard.py` records the change counter of its own writes so the watcher ignores them.

**Tech Stack:** Python 3.12, PyObjC (AppKit NSPanel/NSTimer/NSPasteboard), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-03-clipboard-history-design.md`

## Global Constraints

- Text only; images/files ignored. Whitespace-only skipped.
- Capacity 15, newest first, duplicate moves to top.
- SmartPaste's own clipboard writes are never recorded.
- Pasteboards carrying `org.nspasteboard.ConcealedType` or `org.nspasteboard.TransientType` are skipped.
- Memory only, nothing on disk.
- Run tests with `cd ~/Desktop/Claude\ work/smartpaste && source .venv/bin/activate && python -m pytest tests -q`.
- Never import AppKit at module top level in `history.py` logic paths that tests exercise; inject reads as callables.

---

### Task 1: Ring buffer and age label (`history.py`)

**Files:**
- Create: `smartpaste/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Produces: `HistoryItem(text: str, copied_at: float)`, `ClipboardHistory(capacity=15)` with `push(text, now) -> bool`, `items() -> list[HistoryItem]`, `remove(index)`, `touch(index)`, `__len__`; `age_label(copied_at: float, now: float) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
"""Ring buffer rules for clipboard history."""

from smartpaste.history import ClipboardHistory, age_label


def test_newest_first():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2)
    assert [i.text for i in h.items()] == ["b", "a"]


def test_capacity_drops_oldest():
    h = ClipboardHistory(capacity=3)
    for n in range(5):
        h.push(str(n), now=n)
    assert [i.text for i in h.items()] == ["4", "3", "2"]


def test_duplicate_moves_to_top_without_growing():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2); h.push("a", now=3)
    assert [i.text for i in h.items()] == ["a", "b"]
    assert h.items()[0].copied_at == 3


def test_whitespace_only_is_skipped():
    h = ClipboardHistory()
    assert h.push("   \n\t", now=1) is False
    assert len(h) == 0


def test_remove_by_index():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2); h.push("c", now=3)
    h.remove(1)
    assert [i.text for i in h.items()] == ["c", "a"]


def test_touch_moves_item_to_top():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2); h.push("c", now=3)
    h.touch(2)
    assert [i.text for i in h.items()] == ["a", "c", "b"]


def test_age_label():
    assert age_label(100, now=130) == "now"
    assert age_label(100, now=100 + 5 * 60) == "5m"
    assert age_label(100, now=100 + 3 * 3600) == "3h"
```

- [ ] **Step 2: Run, expect ImportError**

`python -m pytest tests/test_history.py -q` → `ModuleNotFoundError: smartpaste.history`

- [ ] **Step 3: Implement**

```python
"""In-memory clipboard history for SmartPaste.

Keeps the last N text copies, newest first. Nothing is written to disk.
The watcher half (ClipboardWatcher) is added in Task 2.
"""

import time
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
```

- [ ] **Step 4: Run, expect 7 passed**
- [ ] **Step 5: Commit** `git add smartpaste/history.py tests/test_history.py && git commit -m "Add in-memory clipboard history ring buffer"`

---

### Task 2: Own-write tracking and the watcher

**Files:**
- Modify: `smartpaste/clipboard.py` (add `_own_change_count`, `last_own_change_count()`, set it at end of `write_clipboard`)
- Modify: `smartpaste/history.py` (add `ClipboardWatcher`)
- Test: `tests/test_history.py` (append)

**Interfaces:**
- Consumes: `ClipboardHistory.push`.
- Produces: `ClipboardWatcher(history, *, change_count, own_change_count, read_types, read_text)` with `poll() -> bool` (True if an item was recorded) and `start(interval=0.5)`; `clipboard.last_own_change_count() -> int`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_history.py`)

```python
from smartpaste.history import ClipboardWatcher, CONCEALED_TYPES


class FakeBoard:
    def __init__(self):
        self.count = 0
        self.own = -1
        self.types = ["public.utf8-plain-text"]
        self.text = "hello"

    def watcher(self, history):
        return ClipboardWatcher(
            history,
            change_count=lambda: self.count,
            own_change_count=lambda: self.own,
            read_types=lambda: self.types,
            read_text=lambda: self.text,
        )


def test_watcher_records_new_text():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1
    assert w.poll() is True
    assert h.items()[0].text == "hello"


def test_watcher_ignores_unchanged_counter():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; w.poll()
    b.text = "changed but counter did not"
    assert w.poll() is False
    assert len(h) == 1


def test_watcher_skips_smartpaste_own_writes():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; b.own = 1
    assert w.poll() is False
    assert len(h) == 0


def test_watcher_skips_concealed_pasteboards():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; b.types = ["public.utf8-plain-text", CONCEALED_TYPES[0]]
    assert w.poll() is False


def test_watcher_skips_non_text():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; b.text = None; b.types = ["public.png"]
    assert w.poll() is False
```

- [ ] **Step 2: Run, expect ImportError on ClipboardWatcher**

- [ ] **Step 3: Implement**

`clipboard.py`, module level after `log`:
```python
_own_change_count: int = -1


def change_count() -> int:
    return int(NSPasteboard.generalPasteboard().changeCount())


def last_own_change_count() -> int:
    """Change counter of the last write SmartPaste made (so the watcher skips it)."""
    return _own_change_count
```
and at the end of `write_clipboard`, before the log line:
```python
    global _own_change_count
    _own_change_count = int(pb.changeCount())
```

`history.py`, append:
```python
from collections.abc import Callable

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
        count = self._change_count()
        if count == self._last_seen:
            return False
        self._last_seen = count
        if count == self._own_change_count():
            return False
        types = self._read_types()
        if any(t in CONCEALED_TYPES for t in types):
            return False
        text = self._read_text()
        if not text:
            return False
        return self._history.push(text)

    def start(self, interval: float = 0.5) -> None:
        from AppKit import NSTimer
        self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            interval, True, lambda _: self.poll()
        )
```

- [ ] **Step 4: Run all tests, expect 12 in test_history + earlier 17 passing**
- [ ] **Step 5: Commit** `git commit -am "Add clipboard watcher that skips own writes and concealed content"` (add clipboard.py, history.py, test)

---

### Task 3: The history panel (`history_panel.py`)

**Files:**
- Create: `smartpaste/history_panel.py`
- Manual test only (AppKit window). Snippet helper is unit-tested.
- Test: `tests/test_history.py` (append test for `row_label`)

**Interfaces:**
- Consumes: `ClipboardHistory`, `HistoryItem`, `age_label`, `popup._FormatRow`, `popup._CloseButton`, `popup._init_colors`, popup colour globals and layout constants, `preview.PreviewPanel`, `detector.detect`, `constants.ContentType`.
- Produces: `HistoryPanel()` with `show(history, on_pick: Callable[[int], None], on_back: Callable[[], None])`, `dismiss()`, `is_visible`; `row_label(text: str, copied_at: float, now: float) -> str`.

- [ ] **Step 1: Failing test for the row label** (append to `tests/test_history.py`)

```python
from smartpaste.history_panel import row_label


def test_row_label_uses_first_line_collapsed_and_truncated():
    text = "   \n\nName,Age,City\nAlice,30\n"
    assert row_label(text, copied_at=0, now=120) == "Name,Age,City  ·  2m"
    long = "x" * 200
    label = row_label(long, copied_at=0, now=0)
    assert label.startswith("x" * 60) and "…" in label and label.endswith("now")
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement**

```python
"""Clipboard history list panel for SmartPaste.

Opened from the format popup with L. Lists the last copies; Enter makes one
the working text (the app then re-shows the format popup for it).
"""

import logging
import re
from collections.abc import Callable

from AppKit import (
    NSAnimationContext, NSAppearance, NSApplication, NSBackingStoreBuffered,
    NSColor, NSEvent, NSFloatingWindowLevel, NSFont, NSFontWeightSemibold,
    NSMakeRect, NSPanel, NSScreen, NSTextField, NSView, NSVisualEffectView,
    NSWindowStyleMaskBorderless,
)

from smartpaste import popup as pp
from smartpaste.constants import ContentType
from smartpaste.detector import detect
from smartpaste.history import ClipboardHistory, age_label
from smartpaste.preview import PreviewPanel

log = logging.getLogger(__name__)

ROW_HEIGHT = 40
SNIPPET_MAX = 60

TYPE_ICONS: dict[ContentType, str] = {
    ContentType.TABLE: "\U0001F4CA",      # bar chart
    ContentType.MARKDOWN: "\U0001F4DD",   # memo
    ContentType.CODE: "\U0001F4BB",       # laptop
    ContentType.TERMINAL: "\U0001F5A5️",  # desktop computer
    ContentType.PLAIN_TEXT: "\U0001F4C4", # page
}

# Key codes
_KEY_ESC, _KEY_RETURN, _KEY_DOWN, _KEY_UP = 53, 36, 125, 126
_KEY_BACKSPACE, _KEY_DELETE, _KEY_P, _KEY_L = 51, 117, 35, 37
_NUMBER_KEYS = {18: 0, 19: 1, 20: 2, 21: 3, 23: 4, 22: 5, 26: 6, 28: 7, 25: 8}  # 1-9


def row_label(text: str, copied_at: float, now: float | None = None) -> str:
    """First non-empty line, whitespace collapsed, truncated, plus age."""
    first = next((l for l in text.splitlines() if l.strip()), "")
    snippet = re.sub(r"\s+", " ", first.strip())
    if len(snippet) > SNIPPET_MAX:
        snippet = snippet[:SNIPPET_MAX] + "…"
    return f"{snippet}  ·  {age_label(copied_at, now)}"


class HistoryPanel:
    def __init__(self):
        self._panel: NSPanel | None = None
        self._blur: NSVisualEffectView | None = None
        self._monitor = None
        self._rows: list[pp._FormatRow] = []
        self._selected = 0
        self._history: ClipboardHistory | None = None
        self._on_pick: Callable[[int], None] | None = None
        self._on_back: Callable[[], None] | None = None
        self._preview = PreviewPanel()

    @property
    def is_visible(self) -> bool:
        return self._panel is not None

    # ---- building -------------------------------------------------------

    def show(self, history: ClipboardHistory, on_pick, on_back) -> None:
        pp._init_colors()
        if self._panel:
            self.dismiss(keep_callbacks=True)
        self._history, self._on_pick, self._on_back = history, on_pick, on_back
        items = history.items()
        self._selected = min(self._selected, max(0, len(items) - 1))

        rows_h = max(1, len(items)) * ROW_HEIGHT
        height = pp.HEADER_HEIGHT + rows_h + pp.FOOTER_HEIGHT + 12
        sf = NSScreen.mainScreen().frame()
        x = sf.origin.x + (sf.size.width - pp.PANEL_WIDTH) / 2
        y = sf.origin.y + (sf.size.height - height) / 2 + 40
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, pp.PANEL_WIDTH, height), NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered, False)
        panel.setLevel_(NSFloatingWindowLevel + 1)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setBecomesKeyOnlyIfNeeded_(False)
        panel.setCollectionBehavior_(1 << 0 | 1 << 3)
        panel.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))

        blur = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, pp.PANEL_WIDTH, height))
        blur.setMaterial_(9); blur.setBlendingMode_(0); blur.setState_(1)
        blur.setWantsLayer_(True)
        blur.layer().setCornerRadius_(pp.CORNER_RADIUS)
        blur.layer().setMasksToBounds_(True)
        panel.contentView().addSubview_(blur)
        self._blur = blur

        header_y = height - 36
        self._label(blur, "Clipboard History", pp.PADDING_H, header_y, 22,
                    NSFont.systemFontOfSize_weight_(13, NSFontWeightSemibold), pp._CLR_TEXT_SECONDARY)
        blur.addSubview_(pp._CloseButton.alloc_init(
            NSMakeRect(pp.PANEL_WIDTH - 36, header_y - 2, 26, 26), on_click=self._back))
        badge_y = header_y - 18
        count_text = f"{len(items)} of {history._capacity} copies" if items else "Nothing copied yet"
        self._label(blur, count_text, pp.PADDING_H, badge_y, 16, NSFont.systemFontOfSize_(11), pp._CLR_TEXT_DIM)
        sep_y = badge_y - 8
        sep = NSView.alloc().initWithFrame_(NSMakeRect(pp.PADDING_H, sep_y, pp.PANEL_WIDTH - pp.PADDING_H * 2, 1))
        sep.setWantsLayer_(True); sep.layer().setBackgroundColor_(pp._CLR_SEPARATOR.CGColor())
        blur.addSubview_(sep)

        self._rows = []
        for i, item in enumerate(items):
            row_y = sep_y - ROW_HEIGHT * (i + 1) - 4
            row = pp._FormatRow.alloc_init(
                NSMakeRect(0, row_y, pp.PANEL_WIDTH, ROW_HEIGHT),
                label=row_label(item.text, item.copied_at),
                icon=TYPE_ICONS.get(detect(item.text), "\U0001F4C4"),
                shortcut=str(i + 1) if i < 9 else "",
                index=i, on_click=self._pick)
            blur.addSubview_(row)
            self._rows.append(row)
        if self._rows:
            self._rows[self._selected].setSelected_(True)

        hint = ("↑↓ Move    ↩ Use    ⌫ Delete    P Preview    Esc Back"
                if items else "Copy something, then press L again    Esc Back")
        self._label(blur, hint, pp.PADDING_H, 8, 16, NSFont.systemFontOfSize_(10.5), pp._CLR_TEXT_DIM)

        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(1 << 10, self._handle_key)
        self._panel = panel
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel.setAlphaValue_(0.0)
        panel.makeKeyAndOrderFront_(None)
        panel.makeKeyWindow()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.12)
        panel.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()
        log.debug("History panel shown with %d items", len(items))

    @staticmethod
    def _label(parent, text, x, y, h, font, color):
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, pp.PANEL_WIDTH - pp.PADDING_H * 2, h))
        f.setStringValue_(text); f.setBezeled_(False); f.setDrawsBackground_(False)
        f.setEditable_(False); f.setSelectable_(False); f.setFont_(font); f.setTextColor_(color)
        parent.addSubview_(f)
        return f

    def dismiss(self, keep_callbacks: bool = False) -> None:
        if self._preview.is_visible:
            self._preview.dismiss()
        if self._monitor:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        if self._panel:
            self._panel.orderOut_(None)
            self._panel = None
        self._blur = None
        self._rows = []
        if not keep_callbacks:
            self._history = self._on_pick = self._on_back = None

    # ---- actions --------------------------------------------------------

    def _pick(self, index: int) -> None:
        cb = self._on_pick
        self.dismiss()
        if cb:
            cb(index)

    def _back(self) -> None:
        cb = self._on_back
        self.dismiss()
        if cb:
            cb()

    def _delete_selected(self) -> None:
        if not self._history or not self._rows:
            return
        self._history.remove(self._selected)
        self.show(self._history, self._on_pick, self._on_back)

    def _move(self, delta: int) -> None:
        if not self._rows:
            return
        new = max(0, min(len(self._rows) - 1, self._selected + delta))
        if new != self._selected:
            self._rows[self._selected].setSelected_(False)
            self._rows[new].setSelected_(True)
            self._selected = new

    def _handle_key(self, event):
        if self._panel is None or self._preview.is_visible:
            return event  # preview panel owns the keyboard while open
        kc = event.keyCode()
        if kc in (_KEY_ESC, _KEY_L):
            self._back(); return None
        if kc == _KEY_DOWN: self._move(1); return None
        if kc == _KEY_UP: self._move(-1); return None
        if kc == _KEY_RETURN and self._rows: self._pick(self._selected); return None
        if kc in (_KEY_BACKSPACE, _KEY_DELETE): self._delete_selected(); return None
        if kc == _KEY_P and self._rows and self._history:
            self._preview.show(self._history.items()[self._selected].text); return None
        if kc in _NUMBER_KEYS and _NUMBER_KEYS[kc] < len(self._rows):
            self._pick(_NUMBER_KEYS[kc]); return None
        return event
```

- [ ] **Step 4: Run tests, expect pass; `python -c "import smartpaste.history_panel"` imports cleanly**
- [ ] **Step 5: Commit** `git add smartpaste/history_panel.py tests/test_history.py && git commit -m "Add clipboard history panel"`

---

### Task 4: L key in the format popup

**Files:**
- Modify: `smartpaste/popup.py` — `FormatPopup.__init__` (new `_history_callback`), `show()` signature + footer text, `dismiss()` reset, `_handle_key_event()`.

**Interfaces:**
- Produces: `FormatPopup.show(..., on_history: Callable[[], None] | None = None)`; pressing L (keycode 37) dismisses the popup and calls `on_history()`.

- [ ] **Step 1: Edit** (no automated test; UI monitor code)

In `__init__` after `self._ai_callback = None`: `self._history_callback: Callable[[], None] | None = None`.

In `show()` signature add `on_history: Callable[[], None] | None = None,` after `clipboard_text`; set `self._history_callback = on_history` next to `self._ai_callback = on_ai_select`.

Footer string becomes: `"↑↓ Navigate    ↩ Select    P Preview    A AI    L History    Esc Cancel"`.

In `dismiss()` next to `self._ai_callback = None`: `self._history_callback = None`.

In `_handle_key_event`, before the `# P (35)` block:
```python
        # L (37) — open clipboard history
        if keycode == 37 and self._history_callback:
            cb = self._history_callback
            self.dismiss()
            cb()
            return None
```

- [ ] **Step 2: `python -c "import smartpaste.popup"` and full test run stay green**
- [ ] **Step 3: Commit** `git commit -am "Popup: L opens clipboard history"`

---

### Task 5: Wire it up in the app

**Files:**
- Modify: `smartpaste/app.py`

- [ ] **Step 1: Edit**

Imports: add `from smartpaste.history import ClipboardHistory, ClipboardWatcher` and `from smartpaste.history_panel import HistoryPanel`.

In `__init__` after `self._toast = Toast()`:
```python
        self._history = ClipboardHistory()
        self._watcher = ClipboardWatcher(self._history)
        self._history_panel = HistoryPanel()
```

Replace the body of `_on_hotkey` from `content_type = detect(text)` onward with `self._show_popup_for(text)` and add:
```python
    def _show_popup_for(self, text: str) -> None:
        """Show the format popup for *text* (fresh copy or a history pick)."""
        content_type = detect(text)
        log.info("Detected content type: %s", content_type)
        self._popup.show(
            content_type,
            on_select=lambda fmt: self._on_format_selected(text, content_type, fmt),
            on_ai_select=lambda prompt: self._on_ai_rephrase(text, prompt),
            char_count=len(text),
            clipboard_text=text,
            on_history=lambda: self._open_history(text),
        )

    def _open_history(self, current_text: str) -> None:
        """L pressed: swap the popup for the history list."""
        self._history_panel.show(
            self._history,
            on_pick=self._on_history_pick,
            on_back=lambda: self._show_popup_for(current_text),
        )

    def _on_history_pick(self, index: int) -> None:
        """Make the picked item the working text: clipboard + format popup."""
        items = self._history.items()
        if not 0 <= index < len(items):
            return
        text = items[index].text
        self._history.touch(index)
        write_clipboard(plain=text)
        self._show_popup_for(text)
```

In `main()` after `register_hotkey(app._on_hotkey)`: `app._watcher.start()`.

- [ ] **Step 2: Full test run green; `python -c "import smartpaste.app"` imports**
- [ ] **Step 3: Commit** `git commit -am "Wire clipboard history into the app"`

---

### Task 6: Build, install, manual check, changelog

- [ ] **Step 1: Build and install**
```bash
cd ~/Desktop/Claude\ work/smartpaste && source .venv/bin/activate
rm -rf build dist && python setup.py py2app 2>&1 | tail -1
pkill -x SmartPaste; sleep 1; rm -rf /Applications/SmartPaste.app && cp -R dist/SmartPaste.app /Applications/ && open /Applications/SmartPaste.app
```
- [ ] **Step 2: Manual checklist** (the person at the machine does this)
  - Copy three different texts, Cmd+Shift+V, L: three rows, newest first, numbered 1-3.
  - Enter on row 2: format popup returns showing that text's type; Esc, Cmd+V pastes it.
  - L, Backspace: row disappears, count updates.
  - L, P: preview opens; Esc closes only the preview; Esc again goes back to formats.
  - Convert something to Slack, then L: the converted output is not in the list.
  - Copy a password from a password manager, L: not in the list.
  - L with nothing copied since launch: "Nothing copied yet".
- [ ] **Step 3: Changelog** in `~/Desktop/Claude work/Projects/smartpaste/plan.md` under v0.5.0: "Clipboard history: last 15 text copies, L in the popup, Enter makes an item the working text. Memory only."
- [ ] **Step 4: Commit** `git commit -am "Docs: clipboard history"`
