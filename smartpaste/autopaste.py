"""Send Cmd+V to the frontmost app (used by the opt-in "Paste Automatically" setting).

Posting key events needs the Accessibility permission SmartPaste already asks
for (System Settings > Privacy & Security > Accessibility).
"""

import ctypes
import logging

log = logging.getLogger(__name__)

_KEY_V = 9
# Wait for macOS to hand focus back to the previous app after the popup hides.
PASTE_DELAY = 0.2


def accessibility_trusted() -> bool:
    """True if this process may post keyboard events."""
    try:
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except OSError as exc:
        log.warning("Could not check Accessibility permission: %s", exc)
        return False


def post_cmd_v() -> None:
    """Post a Cmd+V key down/up pair. Only Cmd is set, whatever keys are still held."""
    import Quartz

    for key_down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(None, _KEY_V, key_down)
        Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    log.info("Auto-paste: sent Cmd+V")
