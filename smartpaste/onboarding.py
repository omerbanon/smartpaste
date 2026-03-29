"""Onboarding wizard for SmartPaste — 3-step NSWindow setup.

Step 1: API Key — paste key, test connection
Step 2: System Prompt — review/edit the AI instruction
Step 3: Presets & Model — toggle presets, pick model

Shown on first launch (no config) or via Settings... menu item.
"""

from __future__ import annotations

import logging
import threading
import webbrowser

import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFont,
    NSFontWeightMedium,
    NSFontWeightSemibold,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSOffState,
    NSOnState,
    NSPopUpButton,
    NSScrollView,
    NSSecureTextField,
    NSSwitchButton,
    NSTextField,
    NSTextView,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from AppKit import NSAppearance
from Foundation import NSObject
from PyObjCTools.AppHelper import callAfter

from smartpaste.config import (
    AVAILABLE_MODELS,
    DEFAULT_PRESETS,
    DEFAULT_SYSTEM_PROMPT,
    load_config,
    save_config,
)

log = logging.getLogger(__name__)


def _ensure_edit_menu() -> None:
    """Add a standard Edit menu (Cut/Copy/Paste/Select All) so Cmd+V etc. work in text fields.

    Menu bar / accessory apps don't get one automatically.
    """
    app = NSApplication.sharedApplication()
    main_menu = app.mainMenu()
    if not main_menu:
        main_menu = NSMenu.alloc().init()
        app.setMainMenu_(main_menu)

    # Don't add twice
    for item in main_menu.itemArray():
        if item.submenu() and item.submenu().title() == "Edit":
            return

    edit_menu = NSMenu.alloc().initWithTitle_("Edit")
    for title, action, key in [
        ("Cut", "cut:", "x"),
        ("Copy", "copy:", "c"),
        ("Paste", "paste:", "v"),
        ("Select All", "selectAll:", "a"),
        ("Undo", "undo:", "z"),
        ("Redo", "redo:", "Z"),
    ]:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        edit_menu.addItem_(item)

    edit_menu_item = NSMenuItem.alloc().init()
    edit_menu_item.setSubmenu_(edit_menu)
    main_menu.addItem_(edit_menu_item)


WIN_W = 520
WIN_H = 400
PAD = 24
BTN_W = 90
BTN_H = 32


class _ButtonTarget(NSObject):
    """Generic NSObject target to bridge button actions to Python callbacks."""

    def init(self):
        self = objc.super(_ButtonTarget, self).init()
        self._callback = None
        return self

    def setCallback_(self, cb):
        self._callback = cb

    def onAction_(self, sender):
        if self._callback:
            self._callback()


class OnboardingWindow:
    """3-step setup wizard. Call show() to display, optionally pre-filled from existing config."""

    def __init__(self, on_complete: callable | None = None):
        self._window: NSWindow | None = None
        self._on_complete = on_complete
        self._current_step = 0
        self._container: NSView | None = None
        self._targets: list = []  # prevent GC of button targets

        # State held across steps
        self._config = load_config()

        # Step 1 widgets
        self._key_field: NSSecureTextField | None = None
        self._test_label: NSTextField | None = None

        # Step 2 widgets
        self._prompt_text_view: NSTextView | None = None

        # Step 3 widgets
        self._preset_checks: list[tuple[NSButton, str]] = []
        self._custom_field: NSTextField | None = None
        self._model_popup: NSPopUpButton | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Create and display the wizard window."""
        if self._window:
            self._window.makeKeyAndOrderFront_(None)
            return

        _ensure_edit_menu()

        frame = NSMakeRect(0, 0, WIN_W, WIN_H)
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        window.setTitle_("SmartPaste Setup")
        window.center()
        window.setReleasedWhenClosed_(False)

        dark = NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark")
        window.setAppearance_(dark)
        window.contentView().setWantsLayer_(True)
        window.contentView().layer().setBackgroundColor_(
            NSColor.colorWithWhite_alpha_(0.12, 1.0).CGColor()
        )

        self._window = window
        self._current_step = 0
        self._config = load_config()  # refresh
        self._build_step()

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        window.makeKeyAndOrderFront_(None)

    # ------------------------------------------------------------------
    # Step builder
    # ------------------------------------------------------------------

    def _build_step(self) -> None:
        """Build the UI for the current step, replacing the container view."""
        if self._container:
            self._container.removeFromSuperview()

        container = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, WIN_W, WIN_H)
        )
        self._window.contentView().addSubview_(container)
        self._container = container
        self._targets = []

        if self._current_step == 0:
            self._build_step1(container)
        elif self._current_step == 1:
            self._build_step2(container)
        elif self._current_step == 2:
            self._build_step3(container)

    # ------------------------------------------------------------------
    # Step 1: API Key
    # ------------------------------------------------------------------

    def _build_step1(self, container: NSView) -> None:
        y = WIN_H - 60
        self._add_title(container, "Connect to Claude", y)
        y -= 24
        self._add_subtitle(container, "Paste your Anthropic API key to enable AI features", y)

        # Secure text field
        y -= 44
        key_field = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WIN_W - PAD * 2, 28)
        )
        key_field.setPlaceholderString_("sk-ant-api03-...")
        key_field.setFont_(NSFont.systemFontOfSize_(13))
        key_field.setFocusRingType_(1)
        # Pre-fill if we have a saved key
        if self._config.get("api_key"):
            key_field.setStringValue_(self._config["api_key"])
        container.addSubview_(key_field)
        self._key_field = key_field

        # "Get a key" link
        y -= 28
        link = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, 200, 18)
        )
        link.setStringValue_("Get a key \u2192")
        link.setBezeled_(False)
        link.setDrawsBackground_(False)
        link.setEditable_(False)
        link.setSelectable_(False)
        link.setFont_(NSFont.systemFontOfSize_(12))
        link.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.7, 1.0, 1.0))
        container.addSubview_(link)

        # Make the link clickable via a transparent button overlay
        link_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(PAD, y, 200, 18)
        )
        link_btn.setTransparent_(True)
        link_btn.setTarget_(self._make_target(self._open_api_key_page))
        link_btn.setAction_(objc.selector(None, selector=b"onAction:", signature=b"v@:@"))
        container.addSubview_(link_btn)

        # Test Connection button
        y -= 44
        test_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(PAD, y, 140, BTN_H)
        )
        test_btn.setTitle_("Test Connection")
        test_btn.setBezelStyle_(NSBezelStyleRounded)
        test_btn.setTarget_(self._make_target(self._test_connection))
        test_btn.setAction_(objc.selector(None, selector=b"onAction:", signature=b"v@:@"))
        container.addSubview_(test_btn)

        # Status label (right of Test button)
        status = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD + 150, y + 6, WIN_W - PAD * 2 - 150, 20)
        )
        status.setStringValue_("")
        status.setBezeled_(False)
        status.setDrawsBackground_(False)
        status.setEditable_(False)
        status.setSelectable_(False)
        status.setFont_(NSFont.systemFontOfSize_(12))
        container.addSubview_(status)
        self._test_label = status

        # Step indicator + navigation
        self._add_step_indicator(container, 0)
        self._add_nav_buttons(container, show_back=False, next_label="Next")

    def _open_api_key_page(self) -> None:
        webbrowser.open("https://console.anthropic.com/settings/keys")

    def _test_connection(self) -> None:
        """Make a minimal API call to verify the key."""
        key = str(self._key_field.stringValue()).strip()
        if not key:
            self._test_label.setStringValue_("Enter an API key first")
            self._test_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.4, 0.4, 1.0))
            return

        self._test_label.setStringValue_("Testing...")
        self._test_label.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.6))

        def _worker():
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=key, timeout=10.0)
                client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1,
                    messages=[{"role": "user", "content": "hi"}],
                )
                callAfter(self._on_test_result, True, "")
            except Exception as exc:
                callAfter(self._on_test_result, False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_result(self, success: bool, error: str) -> None:
        if not self._test_label:
            return
        if success:
            self._test_label.setStringValue_("\u2705 Connected!")
            self._test_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.9, 0.4, 1.0))
        else:
            msg = error[:60] + "..." if len(error) > 60 else error
            self._test_label.setStringValue_(f"\u274C {msg}")
            self._test_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.4, 0.4, 1.0))

    # ------------------------------------------------------------------
    # Step 2: System Prompt
    # ------------------------------------------------------------------

    def _build_step2(self, container: NSView) -> None:
        y = WIN_H - 60
        self._add_title(container, "AI Behavior", y)
        y -= 24
        self._add_subtitle(container, "This instruction tells Claude how to handle your text", y)

        # Scrollable text view for system prompt
        y -= 180
        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WIN_W - PAD * 2, 170)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setBorderType_(1)  # NSLineBorder

        tv = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, WIN_W - PAD * 2 - 2, 170)
        )
        tv.setFont_(NSFont.systemFontOfSize_(12.5))
        tv.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.88))
        tv.setInsertionPointColor_(NSColor.colorWithWhite_alpha_(1.0, 0.88))
        tv.setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.08, 1.0))
        tv.setEditable_(True)
        tv.setSelectable_(True)
        tv.setRichText_(False)
        tv.setString_(self._config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        tv.setAutoresizingMask_(2)  # flexible width
        tv.textContainer().setWidthTracksTextView_(True)
        scroll.setDocumentView_(tv)
        container.addSubview_(scroll)
        self._prompt_text_view = tv

        # Reset to Default button
        y -= 36
        reset_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(PAD, y, 140, BTN_H)
        )
        reset_btn.setTitle_("Reset to Default")
        reset_btn.setBezelStyle_(NSBezelStyleRounded)
        reset_btn.setTarget_(self._make_target(self._reset_prompt))
        reset_btn.setAction_(objc.selector(None, selector=b"onAction:", signature=b"v@:@"))
        container.addSubview_(reset_btn)

        self._add_step_indicator(container, 1)
        self._add_nav_buttons(container, show_back=True, next_label="Next")

    def _reset_prompt(self) -> None:
        if self._prompt_text_view:
            self._prompt_text_view.setString_(DEFAULT_SYSTEM_PROMPT)

    # ------------------------------------------------------------------
    # Step 3: Presets & Model
    # ------------------------------------------------------------------

    def _build_step3(self, container: NSView) -> None:
        y = WIN_H - 60
        self._add_title(container, "Presets & Model", y)

        # Presets section — checkboxes
        y -= 28
        presets_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, 200, 18)
        )
        presets_label.setStringValue_("Quick presets:")
        presets_label.setBezeled_(False)
        presets_label.setDrawsBackground_(False)
        presets_label.setEditable_(False)
        presets_label.setSelectable_(False)
        presets_label.setFont_(NSFont.systemFontOfSize_weight_(12, NSFontWeightMedium))
        presets_label.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.6))
        container.addSubview_(presets_label)

        saved_presets = self._config.get("presets", DEFAULT_PRESETS)
        all_presets = list(dict.fromkeys(DEFAULT_PRESETS + [p for p in saved_presets if p not in DEFAULT_PRESETS]))

        self._preset_checks = []
        y -= 8
        for preset in all_presets:
            y -= 24
            cb = NSButton.alloc().initWithFrame_(
                NSMakeRect(PAD, y, WIN_W - PAD * 2, 20)
            )
            cb.setButtonType_(NSSwitchButton)
            cb.setTitle_(preset)
            cb.setFont_(NSFont.systemFontOfSize_(12.5))
            cb.setState_(NSOnState if preset in saved_presets else NSOffState)
            container.addSubview_(cb)
            self._preset_checks.append((cb, preset))

        # "Add Custom..." field
        y -= 32
        custom_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, 100, 18)
        )
        custom_label.setStringValue_("Add custom:")
        custom_label.setBezeled_(False)
        custom_label.setDrawsBackground_(False)
        custom_label.setEditable_(False)
        custom_label.setSelectable_(False)
        custom_label.setFont_(NSFont.systemFontOfSize_(12))
        custom_label.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.6))
        container.addSubview_(custom_label)

        y -= 28
        custom_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WIN_W - PAD * 2, 24)
        )
        custom_field.setPlaceholderString_("e.g. Translate to Spanish")
        custom_field.setFont_(NSFont.systemFontOfSize_(12.5))
        container.addSubview_(custom_field)
        self._custom_field = custom_field

        # Model picker
        y -= 36
        model_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, 60, 18)
        )
        model_label.setStringValue_("Model:")
        model_label.setBezeled_(False)
        model_label.setDrawsBackground_(False)
        model_label.setEditable_(False)
        model_label.setSelectable_(False)
        model_label.setFont_(NSFont.systemFontOfSize_weight_(12, NSFontWeightMedium))
        model_label.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.6))
        container.addSubview_(model_label)

        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(PAD + 65, y - 4, WIN_W - PAD * 2 - 65, 26), False
        )
        current_model = self._config.get("model", "claude-haiku-4-5-20251001")
        select_idx = 0
        for i, (model_id, display_name) in enumerate(AVAILABLE_MODELS.items()):
            popup.addItemWithTitle_(f"{display_name}")
            popup.lastItem().setRepresentedObject_(model_id)
            if model_id == current_model:
                select_idx = i
        popup.selectItemAtIndex_(select_idx)
        container.addSubview_(popup)
        self._model_popup = popup

        self._add_step_indicator(container, 2)
        self._add_nav_buttons(container, show_back=True, next_label="Done")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_next(self) -> None:
        """Save current step's data and advance."""
        self._save_step_data()
        if self._current_step < 2:
            self._current_step += 1
            self._build_step()
        else:
            # Done — save config and close
            save_config(self._config)
            self._window.orderOut_(None)
            self._window = None
            if self._on_complete:
                self._on_complete()

    def _go_back(self) -> None:
        self._save_step_data()
        if self._current_step > 0:
            self._current_step -= 1
            self._build_step()

    def _save_step_data(self) -> None:
        """Collect data from current step's widgets into self._config."""
        if self._current_step == 0 and self._key_field:
            self._config["api_key"] = str(self._key_field.stringValue()).strip()
        elif self._current_step == 1 and self._prompt_text_view:
            self._config["system_prompt"] = str(self._prompt_text_view.string())
        elif self._current_step == 2:
            # Presets — only enabled ones
            presets = []
            for cb, preset in self._preset_checks:
                if cb.state() == NSOnState:
                    presets.append(preset)
            # Add custom preset if entered
            if self._custom_field:
                custom = str(self._custom_field.stringValue()).strip()
                if custom and custom not in presets:
                    presets.append(custom)
            self._config["presets"] = presets
            # Model
            if self._model_popup:
                selected = self._model_popup.selectedItem()
                if selected:
                    model_id = selected.representedObject()
                    if model_id:
                        self._config["model"] = str(model_id)

    # ------------------------------------------------------------------
    # Shared UI helpers
    # ------------------------------------------------------------------

    def _add_title(self, container: NSView, text: str, y: float) -> None:
        title = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WIN_W - PAD * 2, 24)
        )
        title.setStringValue_(text)
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setEditable_(False)
        title.setSelectable_(False)
        title.setFont_(NSFont.systemFontOfSize_weight_(18, NSFontWeightSemibold))
        title.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.92))
        container.addSubview_(title)

    def _add_subtitle(self, container: NSView, text: str, y: float) -> None:
        sub = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WIN_W - PAD * 2, 18)
        )
        sub.setStringValue_(text)
        sub.setBezeled_(False)
        sub.setDrawsBackground_(False)
        sub.setEditable_(False)
        sub.setSelectable_(False)
        sub.setFont_(NSFont.systemFontOfSize_(13))
        sub.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.5))
        container.addSubview_(sub)

    def _add_step_indicator(self, container: NSView, current: int) -> None:
        """Draw step dots: 1 · 2 · 3 at the bottom."""
        parts = []
        for i in range(3):
            num = str(i + 1)
            if i == current:
                parts.append(f"[{num}]")
            else:
                parts.append(num)
        indicator_text = "  \u2022  ".join(parts)

        indicator = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PAD, 50, WIN_W - PAD * 2, 16)
        )
        indicator.setStringValue_(indicator_text)
        indicator.setBezeled_(False)
        indicator.setDrawsBackground_(False)
        indicator.setEditable_(False)
        indicator.setSelectable_(False)
        indicator.setFont_(NSFont.systemFontOfSize_(11))
        indicator.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.35))
        indicator.setAlignment_(1)  # center
        container.addSubview_(indicator)

    def _add_nav_buttons(self, container: NSView, show_back: bool, next_label: str) -> None:
        """Add Back / Next (or Done) buttons at the bottom-right."""
        btn_y = 12
        next_x = WIN_W - PAD - BTN_W

        next_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(next_x, btn_y, BTN_W, BTN_H)
        )
        next_btn.setTitle_(next_label)
        next_btn.setBezelStyle_(NSBezelStyleRounded)
        next_btn.setKeyEquivalent_("\r")  # Enter triggers Next/Done
        next_btn.setTarget_(self._make_target(self._go_next))
        next_btn.setAction_(objc.selector(None, selector=b"onAction:", signature=b"v@:@"))
        container.addSubview_(next_btn)

        if show_back:
            back_btn = NSButton.alloc().initWithFrame_(
                NSMakeRect(next_x - BTN_W - 8, btn_y, BTN_W, BTN_H)
            )
            back_btn.setTitle_("Back")
            back_btn.setBezelStyle_(NSBezelStyleRounded)
            back_btn.setTarget_(self._make_target(self._go_back))
            back_btn.setAction_(objc.selector(None, selector=b"onAction:", signature=b"v@:@"))
            container.addSubview_(back_btn)

    def _make_target(self, callback) -> _ButtonTarget:
        """Create a _ButtonTarget wired to callback, preventing GC."""
        target = _ButtonTarget.alloc().init()
        target.setCallback_(callback)
        self._targets.append(target)
        return target
