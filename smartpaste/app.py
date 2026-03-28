"""SmartPaste — macOS menu bar app that converts clipboard content between formats.

Run with:  python -m smartpaste.app

Requires Accessibility permission (System Settings → Privacy & Security → Accessibility)
for global hotkey capture.
"""

import logging
import sys

import rumps
from AppKit import NSApplication

from smartpaste.clipboard import read_clipboard_string, write_clipboard
from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import convert
from smartpaste.detector import detect
from smartpaste.hotkey import register_hotkey
from smartpaste.popup import FormatPopup, Toast, TOAST_ICON_SUCCESS, TOAST_ICON_WARNING, TOAST_ICON_INFO

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


class SmartPasteApp(rumps.App):
    """Menu bar app that registers a global hotkey and shows a format picker."""

    def __init__(self):
        super().__init__(
            name="SmartPaste",
            title="SP",  # menu bar text (Phase 2: replace with template icon)
            quit_button="Quit SmartPaste",
        )
        self._popup = FormatPopup()
        self._toast = Toast()

        # Menu items
        self.menu = [
            rumps.MenuItem("About SmartPaste", callback=self._on_about),
            None,  # separator
        ]

    def _on_about(self, _sender):
        rumps.alert(
            title="SmartPaste",
            message="Clipboard format conversion tool.\nCmd+Shift+V to activate.",
        )

    def _on_hotkey(self) -> None:
        """Called when Cmd+Shift+V is pressed."""
        log.info("Hotkey activated")

        text = read_clipboard_string()
        if not text:
            log.info("Clipboard is empty or has no text, ignoring")
            self._toast.show("No text on clipboard", icon=TOAST_ICON_WARNING)
            return

        content_type = detect(text)
        log.info("Detected content type: %s", content_type)

        if content_type == ContentType.PLAIN_TEXT:
            log.info("Plain text detected, nothing to convert")
            self._toast.show("Plain text — no conversion needed", icon=TOAST_ICON_INFO)
            return

        self._popup.show(
            content_type,
            on_select=lambda fmt: self._on_format_selected(text, content_type, fmt),
            char_count=len(text),
        )

    def _on_format_selected(self, text: str, content_type: ContentType, target_format: TargetFormat) -> None:
        """Called when user picks a format in the popup."""
        log.info("Converting %s → %s", content_type, target_format)

        result = convert(content_type, target_format, text)
        write_clipboard(html=result.get("html"), plain=result.get("plain"))

        log.info("Clipboard updated. Ready to paste.")
        self._toast.show(f"Converted to {target_format.value} — Cmd+V to paste", icon=TOAST_ICON_SUCCESS)


def main():
    # Accessory policy = no Dock icon, activates on CURRENT Space (no Space switching)
    NSApplication.sharedApplication().setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    app = SmartPasteApp()
    register_hotkey(app._on_hotkey)
    app.run()


if __name__ == "__main__":
    main()
