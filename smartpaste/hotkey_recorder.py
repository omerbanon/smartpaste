"""Small window that records a new global shortcut from the next key press."""

import logging
from collections.abc import Callable

from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSEvent,
    NSFont,
    NSMakeRect,
    NSPanel,
    NSTextField,
    NSWindowStyleMaskTitled,
)

from smartpaste.hotkey import KEYCODE_TO_NAME, format_hotkey, normalize_hotkey

log = logging.getLogger(__name__)

_KEY_DOWN_MASK = 1 << 10
_ESC = 53
_FLAG_NAMES = [(1 << 20, "cmd"), (1 << 18, "ctrl"), (1 << 19, "option"), (1 << 17, "shift")]


def spec_from_event(keycode: int, flags: int) -> str | None:
    """Turn a key event into a hotkey spec, or None if the key isn't supported."""
    name = KEYCODE_TO_NAME.get(keycode)
    if name is None:
        return None
    mods = [n for bit, n in _FLAG_NAMES if flags & bit]
    try:
        return normalize_hotkey("+".join(mods + [name]))
    except ValueError:
        return None


class HotkeyRecorder:
    def __init__(self):
        self._panel = None
        self._label = None
        self._monitor = None
        self._on_done: Callable[[str | None], None] | None = None

    def show(self, on_done: Callable[[str | None], None]) -> None:
        """Wait for a shortcut. Calls on_done(spec), or on_done(None) on Esc/close."""
        self._close()
        self._on_done = on_done
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 340, 110),
            NSWindowStyleMaskTitled,  # no close button: Esc cancels, so the hotkey is always restored
            NSBackingStoreBuffered,
            False,
        )
        panel.setTitle_("SmartPaste Hotkey")
        panel.setReleasedWhenClosed_(False)
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 30, 300, 50))
        label.setStringValue_("Press the new shortcut.\nUse Cmd, Ctrl or Option plus a key. Esc cancels.")
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(NSFont.systemFontOfSize_(13))
        label.setAlignment_(1)  # center
        panel.contentView().addSubview_(label)
        panel.center()
        self._panel, self._label = panel, label
        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(_KEY_DOWN_MASK, self._on_key)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel.makeKeyAndOrderFront_(None)

    def _on_key(self, event):
        if self._panel is None:
            return event
        keycode, flags = event.keyCode(), event.modifierFlags()
        if keycode == _ESC and not flags & (1 << 20 | 1 << 18 | 1 << 19):
            self._finish(None)
            return None
        spec = spec_from_event(keycode, flags)
        if spec is None:
            self._label.setStringValue_("That key can't be used.\nUse Cmd, Ctrl or Option plus a letter, digit, F-key or Space.")
            return None
        log.info("Recorded hotkey %s", format_hotkey(spec))
        self._finish(spec)
        return None

    def _finish(self, spec: str | None) -> None:
        cb = self._on_done
        self._close()
        if cb:
            cb(spec)

    def _close(self) -> None:
        if self._monitor is not None:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        if self._panel is not None:
            self._panel.orderOut_(None)
            self._panel = None
        self._label = None
        self._on_done = None
