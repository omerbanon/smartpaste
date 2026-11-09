"""SmartPaste — macOS menu bar app that converts clipboard content between formats.

Run with:  python -m smartpaste.app

Requires Accessibility permission (System Settings → Privacy & Security → Accessibility)
for global hotkey capture.
"""

import logging
import os
import sys
import threading
from pathlib import Path

import rumps
from AppKit import NSApplication, NSImage, NSTimer
from Foundation import NSObject
from PyObjCTools.AppHelper import callAfter

from smartpaste.clipboard import read_clipboard_html, read_clipboard_string, read_clipboard_types, write_clipboard
from smartpaste.config import is_configured, load_config, migrate_api_key_to_keychain, save_config
from smartpaste.constants import IMAGE_PASTEBOARD_TYPES, ContentType, TargetFormat, format_options
from smartpaste.converters import convert
from smartpaste.detector import detect
from smartpaste.history import ClipboardHistory, ClipboardWatcher
from smartpaste.history_panel import HistoryPanel
from smartpaste.hotkey import PRESET_HOTKEYS, HotkeyManager, format_hotkey
from smartpaste.hotkey_recorder import HotkeyRecorder
from smartpaste.onboarding import OnboardingWindow
from smartpaste.popup import FormatPopup, Toast, TOAST_ICON_SUCCESS, TOAST_ICON_WARNING, TOAST_ICON_INFO



def _log_level() -> int:
    """INFO by default. DEBUG when SMARTPASTE_DEBUG=1 or config.json has "debug": true.

    Log lines never include clipboard text or AI prompts, only sizes and types.
    """
    if os.environ.get("SMARTPASTE_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        return logging.DEBUG
    if load_config().get("debug") is True:
        return logging.DEBUG
    return logging.INFO


logging.basicConfig(
    level=_log_level(),
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
        self._history = ClipboardHistory()
        self._watcher = ClipboardWatcher(self._history)
        self._history_panel = HistoryPanel()
        self._ai_generation = 0  # cancellation counter for in-flight AI requests
        self._ai_streaming = False  # True once streamed text is showing in the preview
        self._onboarding: OnboardingWindow | None = None

        self._hotkeys = HotkeyManager(self._on_hotkey)
        self._recorder = HotkeyRecorder()
        self._hotkey_menu = rumps.MenuItem("Hotkey")

        # Menu items
        self._auto_paste_item = rumps.MenuItem("Paste Automatically", callback=self._on_toggle_auto_paste)
        self._auto_paste_item.state = 1 if load_config().get("auto_paste") else 0

        self.menu = [
            rumps.MenuItem("Settings...", callback=self._on_settings),
            self._hotkey_menu,
            self._auto_paste_item,
            None,  # separator
        ]

    def _on_toggle_auto_paste(self, sender) -> None:
        """Off by default: after picking a format, also send Cmd+V to the previous app."""
        enabled = not bool(sender.state)
        sender.state = 1 if enabled else 0
        config = load_config()
        config["auto_paste"] = enabled
        save_config(config)
        if enabled:
            from smartpaste.autopaste import accessibility_trusted

            if not accessibility_trusted():
                self._toast.show(
                    "Grant Accessibility in System Settings for auto-paste", icon=TOAST_ICON_WARNING, duration=3.0
                )

    # ------------------------------------------------------------------
    # Hotkey
    # ------------------------------------------------------------------

    def apply_hotkey(self, spec: str | None) -> None:
        """Register *spec* globally and refresh the Hotkey submenu."""
        spec = self._hotkeys.register(spec)
        menu = self._hotkey_menu
        if len(menu):
            menu.clear()
        options = list(PRESET_HOTKEYS)
        if spec not in options:
            options.append(spec)
        for option in options:
            label = format_hotkey(option) + ("  (default)" if option == PRESET_HOTKEYS[0] else "")
            item = rumps.MenuItem(label, callback=lambda _s, o=option: self._set_hotkey(o))
            item.state = 1 if option == spec else 0
            menu.add(item)
        menu.add(None)
        menu.add(rumps.MenuItem("Record Shortcut...", callback=self._on_record_hotkey))

    def _set_hotkey(self, spec: str) -> None:
        self.apply_hotkey(spec)
        config = load_config()
        config["hotkey"] = self._hotkeys.spec
        save_config(config)
        self._toast.show(f"Hotkey is now {format_hotkey(self._hotkeys.spec)}", icon=TOAST_ICON_SUCCESS)

    def _on_record_hotkey(self, _sender) -> None:
        self._hotkeys.suspend()

        def _done(spec: str | None) -> None:
            if spec:
                self._set_hotkey(spec)
            else:
                self._hotkeys.resume()

        self._recorder.show(_done)

    def _on_settings(self, _sender):
        """Open the onboarding wizard pre-filled with current config."""
        self._onboarding = OnboardingWindow()
        self._onboarding.show()

    def _on_hotkey(self) -> None:
        """Called when the global hotkey (Cmd+Shift+V by default) is pressed."""
        log.info("Hotkey activated")

        text = read_clipboard_string()
        if not text:
            if any(t in IMAGE_PASTEBOARD_TYPES for t in read_clipboard_types()):
                log.info("Clipboard holds an image, no text")
                self._toast.show("Clipboard has an image. SmartPaste converts text only", icon=TOAST_ICON_INFO)
                return
            log.info("Clipboard is empty or has no text, ignoring")
            self._toast.show("No text on clipboard", icon=TOAST_ICON_WARNING)
            return

        self._show_popup_for(text, html=read_clipboard_html())

    def _show_popup_for(self, text: str, html: str | None = None) -> None:
        """Show the format popup for *text* (a fresh copy or a history pick).

        *html* is the clipboard's rich-text version, if any; it enables the
        Markdown target.
        """
        from smartpaste.converters.html_to_md import has_rich_html

        content_type = detect(text)
        rich = has_rich_html(html)
        log.info("Detected content type: %s (rich text: %s)", content_type, rich)
        self._popup.show(
            content_type,
            formats=format_options(content_type, rich),
            on_select=lambda fmt: self._on_format_selected(text, content_type, fmt, html),
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

    def _on_format_selected(
        self, text: str, content_type: ContentType, target_format: TargetFormat, html: str | None = None
    ) -> None:
        """Called when user picks a format in the popup."""
        log.info("Converting %s → %s", content_type, target_format)

        if target_format == TargetFormat.MARKDOWN and html:
            from smartpaste.converters.html_to_md import html_to_markdown

            write_clipboard(plain=html_to_markdown(html))
        else:
            result = convert(content_type, target_format, text)
            write_clipboard(html=result.get("html"), plain=result.get("plain"))
        log.info("Clipboard updated. Ready to paste.")

        if load_config().get("auto_paste"):
            from smartpaste.autopaste import PASTE_DELAY, accessibility_trusted, post_cmd_v

            if accessibility_trusted():
                # The popup just hid; give the previous app a moment to take focus back
                NSTimer.scheduledTimerWithTimeInterval_repeats_block_(PASTE_DELAY, False, lambda _: post_cmd_v())
                self._toast.show(f"Pasted as {target_format.value}", icon=TOAST_ICON_SUCCESS)
                return
            self._toast.show(
                "Auto-paste needs Accessibility permission — Cmd+V to paste", icon=TOAST_ICON_WARNING, duration=3.0
            )
            return

        self._toast.show(f"Converted to {target_format.value} — Cmd+V to paste", icon=TOAST_ICON_SUCCESS)

    def _on_ai_rephrase(self, text: str, prompt: str) -> None:
        """Called when user submits an AI rephrase prompt from the popup."""
        from smartpaste.ai_rephrase import get_api_key

        if not get_api_key():
            self._popup.dismiss()
            self._toast.show("API key not set — open Settings", icon=TOAST_ICON_WARNING)
            return

        # Show loading state in popup until the first text arrives
        self._popup.show_loading()

        # Increment generation counter (used for cancellation)
        self._ai_generation += 1
        generation = self._ai_generation
        self._ai_streaming = False

        def _worker():
            try:
                from smartpaste.ai_rephrase import rephrase
                result = rephrase(
                    prompt,
                    text,
                    on_text=lambda partial: callAfter(self._on_ai_partial, generation, partial),
                    should_stop=lambda: generation != self._ai_generation,
                )
                if result is not None:
                    callAfter(self._on_ai_complete, generation, result, None)
            except Exception as exc:
                log.exception("AI rephrase failed")
                callAfter(self._on_ai_complete, generation, None, exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _cancel_ai(self) -> None:
        """Make the in-flight request stale; the worker stops at its next chunk."""
        self._ai_generation += 1
        self._ai_streaming = False

    def _on_ai_partial(self, generation: int, partial: str) -> None:
        """Main thread: show streamed text as it arrives."""
        if generation != self._ai_generation:
            return
        if not self._ai_streaming:
            # Esc pressed while waiting for the first chunk
            if self._popup._panel is None:
                log.info("AI stream cancelled — popup was dismissed")
                self._cancel_ai()
                return
            self._popup.dismiss()
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            self._popup._preview.show(partial)
            self._ai_streaming = True
            return
        if not self._popup._preview.is_visible:
            log.info("AI stream cancelled — preview was closed")
            self._cancel_ai()
            return
        self._popup._preview.update(partial)

    def _on_ai_complete(self, generation: int, result, error: Exception | None) -> None:
        """Handle AI rephrase completion on the main thread."""
        # Ignore stale results (user pressed Esc during loading, or new request started)
        if generation != self._ai_generation:
            log.info("AI result discarded (generation %d, current %d)", generation, self._ai_generation)
            return

        streaming, self._ai_streaming = self._ai_streaming, False
        preview = self._popup._preview

        if error:
            if not streaming:
                if self._popup._panel is None:
                    return  # dismissed while loading
                self._popup.dismiss()
            msg = str(error)
            if len(msg) > 60:
                msg = msg[:57] + "..."
            self._toast.show(f"AI error: {msg}", icon=TOAST_ICON_WARNING, duration=3.0)
            return

        note = None
        if result.truncated:
            note = "The response hit the length limit and is cut off. Try a shorter text or split it."

        if streaming:
            if preview.is_visible:
                preview.update(result.text, note=note)
            return

        # No partial text was shown (very short reply): show the result now
        if self._popup._panel is None:
            log.info("AI result discarded — popup was dismissed")
            return
        self._popup.dismiss()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        preview.show(result.text, note=note)


def main():
    # Accessory policy = no Dock icon, activates on CURRENT Space (no Space switching)
    NSApplication.sharedApplication().setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    migrate_api_key_to_keychain()
    app = SmartPasteApp()
    app.apply_hotkey(load_config().get("hotkey"))
    app._watcher.start()

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
