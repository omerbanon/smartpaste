"""Global Cmd+Shift+V hotkey registration via quickmachotkey."""

import logging
from collections.abc import Callable

from quickmachotkey import quickHotKey
from quickmachotkey.constants import cmdKey, shiftKey, kVK_ANSI_V

log = logging.getLogger(__name__)


def register_hotkey(callback: Callable[[], None]) -> None:
    """Register Cmd+Shift+V as a global hotkey.

    `callback` is invoked (on the main thread) whenever the combo is pressed.
    Must be called after the NSApplication run loop is started (rumps handles this).
    """
    @quickHotKey(virtualKey=kVK_ANSI_V, modifierMask=cmdKey | shiftKey)
    def _on_hotkey() -> None:
        log.debug("Hotkey Cmd+Shift+V triggered")
        callback()

    log.info("Global hotkey Cmd+Shift+V registered")
