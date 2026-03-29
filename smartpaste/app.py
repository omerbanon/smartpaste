"""SmartPaste — macOS menu bar app that converts clipboard content between formats.

Run with:  python -m smartpaste.app

Requires Accessibility permission (System Settings → Privacy & Security → Accessibility)
for global hotkey capture.
"""

import logging
import sys
import threading
from pathlib import Path

import rumps
from AppKit import NSApplication, NSImage
from Foundation import NSObject
from PyObjCTools.AppHelper import callAfter

from smartpaste.clipboard import read_clipboard_string, write_clipboard
from smartpaste.config import is_configured
from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import convert
from smartpaste.detector import detect
from smartpaste.hotkey import register_hotkey
from smartpaste.onboarding import OnboardingWindow
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
        icon_path = str(Path(__file__).parent / "icon.png")
        super().__init__(
            name="SmartPaste",
            icon=icon_path,
            template=True,
            title="",
            quit_button="Quit SmartPaste",
        )
        self._popup = FormatPopup()
        self._toast = Toast()
        self._ai_generation = 0  # cancellation counter for in-flight AI requests
        self._onboarding: OnboardingWindow | None = None

        # Menu items
        self.menu = [
            rumps.MenuItem("Settings...", callback=self._on_settings),
            None,  # separator
        ]

    def _on_settings(self, _sender):
        """Open the onboarding wizard pre-filled with current config."""
        self._onboarding = OnboardingWindow()
        self._onboarding.show()

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

        self._popup.show(
            content_type,
            on_select=lambda fmt: self._on_format_selected(text, content_type, fmt),
            on_ai_select=lambda prompt: self._on_ai_rephrase(text, prompt),
            char_count=len(text),
            clipboard_text=text,
        )

    def _on_format_selected(self, text: str, content_type: ContentType, target_format: TargetFormat) -> None:
        """Called when user picks a format in the popup."""
        log.info("Converting %s → %s", content_type, target_format)

        result = convert(content_type, target_format, text)
        write_clipboard(html=result.get("html"), plain=result.get("plain"))

        log.info("Clipboard updated. Ready to paste.")
        self._toast.show(f"Converted to {target_format.value} — Cmd+V to paste", icon=TOAST_ICON_SUCCESS)

    def _on_ai_rephrase(self, text: str, prompt: str) -> None:
        """Called when user submits an AI rephrase prompt from the popup."""
        from smartpaste.ai_rephrase import get_api_key

        if not get_api_key():
            self._popup.dismiss()
            self._toast.show("API key not set — open Settings", icon=TOAST_ICON_WARNING)
            return

        # Show loading state in popup
        self._popup.show_loading()

        # Increment generation counter (used for cancellation)
        self._ai_generation += 1
        generation = self._ai_generation

        def _worker():
            try:
                from smartpaste.ai_rephrase import rephrase
                result = rephrase(prompt, text)
                callAfter(self._on_ai_complete, generation, result, None)
            except Exception as exc:
                log.exception("AI rephrase failed")
                callAfter(self._on_ai_complete, generation, None, exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _on_ai_complete(self, generation: int, result: str | None, error: Exception | None) -> None:
        """Handle AI rephrase completion on the main thread."""
        # Ignore stale results (user pressed Esc during loading, or new request started)
        if generation != self._ai_generation:
            log.info("AI result discarded (generation %d, current %d)", generation, self._ai_generation)
            return

        # If popup was already dismissed (user pressed Esc), discard result
        if self._popup._panel is None:
            log.info("AI result discarded — popup was dismissed")
            return

        self._popup.dismiss()

        if error:
            msg = str(error)
            if len(msg) > 60:
                msg = msg[:57] + "..."
            self._toast.show(f"AI error: {msg}", icon=TOAST_ICON_WARNING, duration=3.0)
            return

        # Show result in the preview panel — need to re-activate since dismiss() hid the app
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._popup._preview.show(result)


def main():
    # Accessory policy = no Dock icon, activates on CURRENT Space (no Space switching)
    NSApplication.sharedApplication().setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    app = SmartPasteApp()
    register_hotkey(app._on_hotkey)

    # Show onboarding wizard on first launch (no config file or no API key)
    if not is_configured():
        from AppKit import NSTimer
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            0.5, False, lambda _: _show_initial_onboarding(app)
        )

    app.run()


def _show_initial_onboarding(app: SmartPasteApp) -> None:
    """Show the onboarding wizard for first-time setup."""
    app._onboarding = OnboardingWindow()
    app._onboarding.show()


if __name__ == "__main__":
    main()
