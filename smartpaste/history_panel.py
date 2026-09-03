"""Clipboard history list panel for SmartPaste.

Opened from the format popup with L. Lists the last copies; Enter makes one
the working text (the app then re-shows the format popup for it).
"""

import logging
import re
from collections.abc import Callable

from AppKit import (
    NSAnimationContext,
    NSAppearance,
    NSApplication,
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSFont,
    NSFontWeightSemibold,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSTextField,
    NSView,
    NSVisualEffectView,
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
    ContentType.TABLE: "\U0001F4CA",       # bar chart
    ContentType.MARKDOWN: "\U0001F4DD",    # memo
    ContentType.CODE: "\U0001F4BB",        # laptop
    ContentType.TERMINAL: "\U0001F5A5",    # desktop computer
    ContentType.PLAIN_TEXT: "\U0001F4C4",  # page
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
    """Dark panel listing recent copies. Same look as the format popup."""

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

    def show(
        self,
        history: ClipboardHistory,
        on_pick: Callable[[int], None],
        on_back: Callable[[], None],
    ) -> None:
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
            NSMakeRect(x, y, pp.PANEL_WIDTH, height),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSFloatingWindowLevel + 1)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setBecomesKeyOnlyIfNeeded_(False)
        panel.setCollectionBehavior_(1 << 0 | 1 << 3)
        panel.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))

        blur = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, pp.PANEL_WIDTH, height))
        blur.setMaterial_(9)
        blur.setBlendingMode_(0)
        blur.setState_(1)
        blur.setWantsLayer_(True)
        blur.layer().setCornerRadius_(pp.CORNER_RADIUS)
        blur.layer().setMasksToBounds_(True)
        panel.contentView().addSubview_(blur)
        self._blur = blur

        # Header, close button, count line, separator
        header_y = height - 36
        self._label(blur, "Clipboard History", header_y, 22,
                    NSFont.systemFontOfSize_weight_(13, NSFontWeightSemibold), pp._CLR_TEXT_SECONDARY)
        blur.addSubview_(pp._CloseButton.alloc_init(
            NSMakeRect(pp.PANEL_WIDTH - 36, header_y - 2, 26, 26), on_click=self._back))
        badge_y = header_y - 18
        count_text = f"{len(items)} of {history.capacity} copies" if items else "Nothing copied yet"
        self._label(blur, count_text, badge_y, 16, NSFont.systemFontOfSize_(11), pp._CLR_TEXT_DIM)
        sep_y = badge_y - 8
        sep = NSView.alloc().initWithFrame_(
            NSMakeRect(pp.PADDING_H, sep_y, pp.PANEL_WIDTH - pp.PADDING_H * 2, 1))
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(pp._CLR_SEPARATOR.CGColor())
        blur.addSubview_(sep)

        # Rows
        self._rows = []
        for i, item in enumerate(items):
            row_y = sep_y - ROW_HEIGHT * (i + 1) - 4
            row = pp._FormatRow.alloc_init(
                NSMakeRect(0, row_y, pp.PANEL_WIDTH, ROW_HEIGHT),
                label=row_label(item.text, item.copied_at),
                icon=TYPE_ICONS.get(detect(item.text), "\U0001F4C4"),
                shortcut=str(i + 1) if i < 9 else "",
                index=i,
                on_click=self._pick,
            )
            blur.addSubview_(row)
            self._rows.append(row)
        if self._rows:
            self._rows[self._selected].setSelected_(True)

        # Footer
        hint = ("↑↓ Move    ↩ Use    ⌫ Delete    P Preview    Esc Back"
                if items else "Copy something, then press L again    Esc Back")
        self._label(blur, hint, 8, 16, NSFont.systemFontOfSize_(10.5), pp._CLR_TEXT_DIM)

        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            1 << 10, self._handle_key)
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
    def _label(parent, text: str, y: float, h: float, font, color) -> NSTextField:
        f = NSTextField.alloc().initWithFrame_(
            NSMakeRect(pp.PADDING_H, y, pp.PANEL_WIDTH - pp.PADDING_H * 2, h))
        f.setStringValue_(text)
        f.setBezeled_(False)
        f.setDrawsBackground_(False)
        f.setEditable_(False)
        f.setSelectable_(False)
        f.setFont_(font)
        f.setTextColor_(color)
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
            return event  # the preview panel owns the keyboard while open
        kc = event.keyCode()
        if kc in (_KEY_ESC, _KEY_L):
            self._back()
            return None
        if kc == _KEY_DOWN:
            self._move(1)
            return None
        if kc == _KEY_UP:
            self._move(-1)
            return None
        if kc == _KEY_RETURN and self._rows:
            self._pick(self._selected)
            return None
        if kc in (_KEY_BACKSPACE, _KEY_DELETE):
            self._delete_selected()
            return None
        if kc == _KEY_P and self._rows and self._history:
            self._preview.show(self._history.items()[self._selected].text)
            return None
        if kc in _NUMBER_KEYS and _NUMBER_KEYS[kc] < len(self._rows):
            self._pick(_NUMBER_KEYS[kc])
            return None
        return event
