"""Command-palette style popup panel for SmartPaste.

Dark translucent panel with format options, keyboard navigation (Up/Down/1-6/Enter/Esc),
and mouse hover/click. Styled after VS Code / Raycast command palette.
Includes AI rephrase sub-panel with text input and preset chips.
"""

import logging
from collections.abc import Callable

import objc
from AppKit import (
    NSAnimationContext,
    NSApplication,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSFont,
    NSFontWeightMedium,
    NSFontWeightRegular,
    NSFontWeightSemibold,
    NSMakeRect,
    NSNonactivatingPanelMask,
    NSPanel,
    NSScreen,
    NSScrollView,
    NSTextField,
    NSTextView,
    NSTrackingActiveAlways,
    NSTrackingArea,
    NSTrackingMouseEnteredAndExited,
    NSTrackingMouseMoved,
    NSView,
    NSVisualEffectView,
    NSWindowStyleMaskBorderless,
)
from AppKit import NSAppearance, NSCenterTextAlignment, NSTimer
from Foundation import NSObject

from WebKit import WKWebView, WKWebViewConfiguration

from smartpaste.constants import (
    ContentType, TargetFormat, FORMAT_OPTIONS, CONTENT_TYPE_LABELS, get_ai_presets,
)
from smartpaste.preview import PreviewPanel, _render_to_html, _CopyButton


class _FieldActionTarget(NSObject):
    """NSObject helper to receive NSTextField action (Enter key) from the AI input."""

    def init(self):
        self = objc.super(_FieldActionTarget, self).init()
        self._callback = None
        return self

    def setCallback_(self, callback):
        self._callback = callback

    def onAction_(self, sender):
        if self._callback:
            self._callback()


class _AITextDelegate(NSObject):
    """NSTextView delegate that hides the placeholder label when text is entered."""

    _placeholder = objc.ivar()

    def textDidChange_(self, notification):
        tv = notification.object()
        text = str(tv.string())
        if self._placeholder:
            self._placeholder.setHidden_(len(text) > 0)


class _AIPanel(NSPanel):
    """Custom NSPanel that intercepts Esc and Enter via sendEvent_ so we don't
    need a local event monitor (which steals keystrokes from the text view)."""

    _esc_callback = objc.ivar()
    _enter_callback = objc.ivar()
    _down_callback = objc.ivar()
    _up_callback = objc.ivar()

    def canBecomeKeyWindow(self):
        return True

    def sendEvent_(self, event):
        # Only intercept KeyDown events
        if event.type() == 10:  # NSEventTypeKeyDown
            kc = event.keyCode()
            if kc == 53 and callable(self._esc_callback):  # Esc
                self._esc_callback()
                return
            if kc == 36 and callable(self._enter_callback):  # Enter
                self._enter_callback()
                return
            if kc == 125 and callable(self._down_callback):  # Down arrow
                self._down_callback()
                return
            if kc == 126 and callable(self._up_callback):  # Up arrow
                self._up_callback()
                return
        objc.super(_AIPanel, self).sendEvent_(event)

log = logging.getLogger(__name__)

# Layout constants
PANEL_WIDTH = 560
ROW_HEIGHT = 44
ROW_INSET = 8        # horizontal inset for row highlight
ROW_PADDING = 6      # vertical padding inside rows
HEADER_HEIGHT = 52    # header area including padding
FOOTER_HEIGHT = 32    # bottom hint bar
CORNER_RADIUS = 12
PADDING_H = 16        # horizontal padding for text

# Inline preview section
PREVIEW_SECTION_HEIGHT = 400
PREVIEW_TITLE_HEIGHT = 32
PREVIEW_TOTAL_HEIGHT = PREVIEW_SECTION_HEIGHT + PREVIEW_TITLE_HEIGHT + 1  # +1 separator

# AI sub-panel layout
AI_PANEL_HEIGHT = 340
AI_INPUT_HEIGHT = 28
AI_CHIP_HEIGHT = 28
AI_CHIP_GAP = 8
AI_CHIP_PADDING_H = 14

# Colors (dark theme)
_CLR_BG_SELECTED = None       # lazy init
_CLR_BG_HOVER = None
_CLR_TEXT_PRIMARY = None
_CLR_TEXT_SECONDARY = None
_CLR_TEXT_DIM = None
_CLR_SEPARATOR = None
_CLR_BADGE_BG = None
_CLR_BADGE_TEXT = None


def _init_colors():
    """Initialize colors lazily (needs AppKit loaded)."""
    global _CLR_BG_SELECTED, _CLR_BG_HOVER, _CLR_TEXT_PRIMARY, _CLR_TEXT_SECONDARY
    global _CLR_TEXT_DIM, _CLR_SEPARATOR, _CLR_BADGE_BG, _CLR_BADGE_TEXT
    _CLR_BG_SELECTED = NSColor.colorWithWhite_alpha_(1.0, 0.12)
    _CLR_BG_HOVER = NSColor.colorWithWhite_alpha_(1.0, 0.06)
    _CLR_TEXT_PRIMARY = NSColor.colorWithWhite_alpha_(1.0, 0.92)
    _CLR_TEXT_SECONDARY = NSColor.colorWithWhite_alpha_(1.0, 0.55)
    _CLR_TEXT_DIM = NSColor.colorWithWhite_alpha_(1.0, 0.30)
    _CLR_SEPARATOR = NSColor.colorWithWhite_alpha_(1.0, 0.10)
    _CLR_BADGE_BG = NSColor.colorWithWhite_alpha_(1.0, 0.08)
    _CLR_BADGE_TEXT = NSColor.colorWithWhite_alpha_(1.0, 0.40)


# Format icons (emoji — lightweight, no SF Symbols dependency)
FORMAT_ICONS: dict[TargetFormat, str] = {
    TargetFormat.GOOGLE_DOCS: "\U0001F4DD",   # memo
    TargetFormat.GMAIL: "\U0001F4E8",          # incoming envelope (colorful)
    TargetFormat.SLACK: "\U0001F4AC",          # speech bubble
    TargetFormat.CLI: "\U0001F4BB",             # laptop (terminal)
    TargetFormat.PLAIN: "\U0001F4CB",          # clipboard
    TargetFormat.AI_REPHRASE: "\U0001F9E0",   # brain
}


class _FormatRow(NSView):
    """A single format option row with hover/selection highlighting."""

    @classmethod
    def alloc_init(cls, frame, label: str, icon: str, shortcut: str,
                   index: int, on_click: Callable[[int], None]):
        self = cls.alloc().initWithFrame_(frame)
        self._index = index
        self._on_click = on_click
        self._highlighted = False
        self._selected = False

        content_x = ROW_INSET
        content_w = frame.size.width - ROW_INSET * 2
        content_h = frame.size.height

        # Vertical centering: fixed text height, calculate y offset
        icon_h = 22
        text_h = 20
        icon_y = (content_h - icon_h) / 2
        text_y = (content_h - text_h) / 2

        # Icon label (emoji)
        icon_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(content_x + 12, icon_y, 28, icon_h)
        )
        icon_field.setStringValue_(icon)
        icon_field.setBezeled_(False)
        icon_field.setDrawsBackground_(False)
        icon_field.setEditable_(False)
        icon_field.setSelectable_(False)
        icon_field.setFont_(NSFont.systemFontOfSize_(16))
        self.addSubview_(icon_field)

        # Format name
        name_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(content_x + 44, text_y, content_w - 100, text_h)
        )
        name_field.setStringValue_(label)
        name_field.setBezeled_(False)
        name_field.setDrawsBackground_(False)
        name_field.setEditable_(False)
        name_field.setSelectable_(False)
        name_field.setFont_(NSFont.systemFontOfSize_weight_(14, NSFontWeightRegular))
        name_field.setTextColor_(_CLR_TEXT_PRIMARY)
        self.addSubview_(name_field)
        self._name_field = name_field

        # Shortcut badge (right side)
        badge_w = 24
        badge_x = frame.size.width - ROW_INSET - badge_w - 12
        badge_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(badge_x, (content_h - 20) / 2, badge_w, 20)
        )
        badge_field.setStringValue_(shortcut)
        badge_field.setBezeled_(False)
        badge_field.setDrawsBackground_(False)
        badge_field.setEditable_(False)
        badge_field.setSelectable_(False)
        badge_field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, NSFontWeightMedium))
        badge_field.setTextColor_(_CLR_BADGE_TEXT)
        badge_field.setAlignment_(1)  # center
        self.addSubview_(badge_field)
        self._badge_field = badge_field

        # Tracking area for hover
        tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(),
            NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways,
            self,
            None,
        )
        self.addTrackingArea_(tracking)

        return self

    def setHighlighted_(self, val: bool):
        self._highlighted = val
        self.setNeedsDisplay_(True)

    def setSelected_(self, val: bool):
        self._selected = val
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        # Draw highlight background within inset area
        inset_rect = NSMakeRect(
            ROW_INSET, 2,
            self.bounds().size.width - ROW_INSET * 2,
            self.bounds().size.height - 4
        )
        if self._selected:
            _CLR_BG_SELECTED.set()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset_rect, 6, 6)
            path.fill()
        elif self._highlighted:
            _CLR_BG_HOVER.set()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset_rect, 6, 6)
            path.fill()

    def mouseEntered_(self, event):
        self.setHighlighted_(True)

    def mouseExited_(self, event):
        self.setHighlighted_(False)

    def mouseDown_(self, event):
        self._on_click(self._index)


class _PresetChip(NSView):
    """Full-width row for AI preset prompts (command-palette result style)."""

    @classmethod
    def alloc_init(cls, frame, label: str, on_click: Callable[[str], None]):
        self = cls.alloc().initWithFrame_(frame)
        self._label = label
        self._on_click = on_click
        self._highlighted = False
        self._selected = False

        content_h = frame.size.height
        text_h = 20
        text_y = (content_h - text_h) / 2

        # Row label — left-aligned with padding
        text_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(ROW_INSET + 16, text_y,
                       frame.size.width - ROW_INSET * 2 - 32, text_h)
        )
        text_field.setStringValue_(label)
        text_field.setBezeled_(False)
        text_field.setDrawsBackground_(False)
        text_field.setEditable_(False)
        text_field.setSelectable_(False)
        text_field.setFont_(NSFont.systemFontOfSize_weight_(13.5, NSFontWeightRegular))
        text_field.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.78))
        self.addSubview_(text_field)

        # Tracking area for hover
        tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(),
            NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways,
            self,
            None,
        )
        self.addTrackingArea_(tracking)

        return self

    def setSelected_(self, val: bool):
        self._selected = val
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        if self._selected or self._highlighted:
            inset = NSMakeRect(
                ROW_INSET, 2,
                self.bounds().size.width - ROW_INSET * 2,
                self.bounds().size.height - 4,
            )
            NSColor.colorWithWhite_alpha_(1.0, 0.10).set()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset, 6, 6)
            path.fill()

    def mouseEntered_(self, event):
        self._highlighted = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        self._highlighted = False
        self.setNeedsDisplay_(True)

    def mouseDown_(self, event):
        self._on_click(self._label)


def _measure_chip_width(text: str) -> float:
    """Estimate chip width based on text length."""
    # ~7px per char at 12px font + padding
    return len(text) * 7.0 + AI_CHIP_PADDING_H * 2 + 4


class FormatPopup:
    """Manages the command-palette style format selection panel."""

    def __init__(self):
        self._panel: NSPanel | None = None
        self._buttons: list[_FormatRow] = []
        self._selected_index: int = 0
        self._formats: list[TargetFormat] = []
        self._callback: Callable[[TargetFormat], None] | None = None
        self._ai_callback: Callable[[str], None] | None = None
        self._local_monitor = None
        self._global_monitor = None
        self._preview = PreviewPanel()
        self._clipboard_text: str = ""
        self._ai_mode = False
        self._ai_input: NSTextField | None = None
        self._ai_text_view: NSTextView | None = None
        self._blur_view: NSVisualEffectView | None = None
        self._loading = False
        self._loading_timer: NSTimer | None = None
        self._loading_label: NSTextField | None = None
        self._dot_count = 0
        self._field_action_target: _FieldActionTarget | None = None
        self._ai_text_delegate: _AITextDelegate | None = None
        self._ai_chips: list[_PresetChip] = []
        self._ai_selected_index: int = -1  # -1 = text input focused, 0+ = preset row
        self._transitioning = False  # guard: ignore global clicks during AI panel swap
        # Inline preview state
        self._preview_visible = False
        self._preview_webview: WKWebView | None = None
        self._preview_title_bar: NSView | None = None
        self._preview_separator: NSView | None = None
        self._preview_copy_btn: _CopyButton | None = None
        self._preview_loaded_text: str = ""
        self._base_panel_height: float = 0
        self._footer_field: NSTextField | None = None
        self._preview_animating = False

    def show(
        self,
        content_type: ContentType,
        on_select: Callable[[TargetFormat], None],
        on_ai_select: Callable[[str], None] | None = None,
        char_count: int = 0,
        clipboard_text: str = "",
    ) -> None:
        """Display the popup with format options for the given content type."""
        _init_colors()

        # Dismiss any existing popup first
        if self._panel:
            self.dismiss()

        self._formats = FORMAT_OPTIONS.get(content_type, [TargetFormat.PLAIN])
        self._callback = on_select
        self._ai_callback = on_ai_select
        self._selected_index = 0
        self._clipboard_text = clipboard_text
        self._ai_mode = False
        self._loading = False
        self._preview_visible = False
        self._preview_animating = False

        num_rows = len(self._formats)
        panel_height = HEADER_HEIGHT + num_rows * ROW_HEIGHT + FOOTER_HEIGHT + 12
        self._base_panel_height = panel_height

        # Center on screen, upper third
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = sf.origin.x + (sf.size.width - PANEL_WIDTH) / 2
        y = sf.origin.y + sf.size.height * 0.6

        frame = NSMakeRect(x, y, PANEL_WIDTH, panel_height)

        # Create panel — borderless, floating above all windows
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSFloatingWindowLevel + 1)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setMovableByWindowBackground_(False)
        panel.setBecomesKeyOnlyIfNeeded_(False)  # always accept keyboard focus
        # Appear on whichever Space/desktop the user is currently on
        panel.setCollectionBehavior_(1 << 0 | 1 << 3)  # canJoinAllSpaces | transient

        # Force dark appearance
        dark_appearance = NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark")
        panel.setAppearance_(dark_appearance)

        # Visual effect view (translucent dark blur)
        content_frame = NSMakeRect(0, 0, PANEL_WIDTH, panel_height)
        blur_view = NSVisualEffectView.alloc().initWithFrame_(content_frame)
        blur_view.setMaterial_(9)  # NSVisualEffectMaterialHUDWindow — dark translucent
        blur_view.setBlendingMode_(0)  # behindWindow
        blur_view.setState_(1)  # active
        blur_view.setWantsLayer_(True)
        blur_view.layer().setCornerRadius_(CORNER_RADIUS)
        blur_view.layer().setMasksToBounds_(True)

        panel.contentView().addSubview_(blur_view)
        self._blur_view = blur_view

        # --- Header ---
        header_y = panel_height - 36
        header = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, header_y, PANEL_WIDTH - PADDING_H * 2, 22)
        )
        header.setStringValue_("Paste as...")
        header.setBezeled_(False)
        header.setDrawsBackground_(False)
        header.setEditable_(False)
        header.setSelectable_(False)
        header.setFont_(NSFont.systemFontOfSize_weight_(13, NSFontWeightSemibold))
        header.setTextColor_(_CLR_TEXT_SECONDARY)
        blur_view.addSubview_(header)

        # Content type badge: "Markdown  ·  247 chars"
        badge_y = header_y - 18
        type_label = CONTENT_TYPE_LABELS.get(content_type, "Content")
        badge_text = type_label.replace(" Detected", "")
        if char_count > 0:
            badge_text += f"  \u00B7  {char_count:,} chars"
        badge = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, badge_y, PANEL_WIDTH - PADDING_H * 2, 16)
        )
        badge.setStringValue_(badge_text)
        badge.setBezeled_(False)
        badge.setDrawsBackground_(False)
        badge.setEditable_(False)
        badge.setSelectable_(False)
        badge.setFont_(NSFont.systemFontOfSize_(11))
        badge.setTextColor_(_CLR_TEXT_DIM)
        blur_view.addSubview_(badge)

        # --- Separator ---
        sep_y = badge_y - 8
        sep = NSView.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, sep_y, PANEL_WIDTH - PADDING_H * 2, 1)
        )
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(_CLR_SEPARATOR.CGColor())
        blur_view.addSubview_(sep)

        # --- Format rows ---
        self._buttons = []
        for i, fmt in enumerate(self._formats):
            btn_y = sep_y - ROW_HEIGHT * (i + 1) - 4
            icon = FORMAT_ICONS.get(fmt, "\U0001F4CB")
            # Show "A" as shortcut badge for AI_REPHRASE, number for others
            if fmt == TargetFormat.AI_REPHRASE:
                shortcut = "A"
            else:
                shortcut = str(i + 1)
            btn = _FormatRow.alloc_init(
                NSMakeRect(0, btn_y, PANEL_WIDTH, ROW_HEIGHT),
                label=fmt.value,
                icon=icon,
                shortcut=shortcut,
                index=i,
                on_click=self._on_button_click,
            )
            blur_view.addSubview_(btn)
            self._buttons.append(btn)

        # Highlight first option
        if self._buttons:
            self._buttons[0].setSelected_(True)

        # --- Footer hint bar ---
        footer = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, 8, PANEL_WIDTH - PADDING_H * 2, 16)
        )
        footer.setStringValue_("\u2191\u2193 Navigate    \u21A9 Select    P Preview    A AI    Esc Cancel")
        footer.setBezeled_(False)
        footer.setDrawsBackground_(False)
        footer.setEditable_(False)
        footer.setSelectable_(False)
        footer.setFont_(NSFont.systemFontOfSize_(10.5))
        footer.setTextColor_(_CLR_TEXT_DIM)
        blur_view.addSubview_(footer)
        self._footer_field = footer

        # --- Event monitors ---
        # Local monitor for keyboard events
        self._local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            1 << 10,  # NSKeyDownMask
            self._handle_key_event,
        )
        # Global monitor to dismiss on click outside
        self._global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            (1 << 1) | (1 << 3),  # NSLeftMouseDownMask | NSRightMouseDownMask
            self._handle_global_click,
        )

        self._panel = panel

        # Activate our app so the panel receives keyboard events
        # (like Spotlight/Raycast — activate on show, hide on dismiss)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

        # Fade-in animation
        panel.setAlphaValue_(0.0)
        panel.makeKeyAndOrderFront_(None)
        panel.makeKeyWindow()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.12)
        panel.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

        log.debug("Popup shown with %d format options", len(self._formats))

    def dismiss(self) -> None:
        """Close the popup and return focus to the previous app."""
        if self._preview.is_visible:
            self._preview.dismiss()
        # Clean up inline preview
        self._preview_visible = False
        self._preview_animating = False
        if self._preview_webview:
            self._preview_webview.removeFromSuperview()
            self._preview_webview = None
        if self._preview_title_bar:
            self._preview_title_bar.removeFromSuperview()
            self._preview_title_bar = None
        if self._preview_separator:
            self._preview_separator.removeFromSuperview()
            self._preview_separator = None
        self._preview_copy_btn = None
        self._footer_field = None
        self._stop_loading_animation()
        if self._local_monitor:
            NSEvent.removeMonitor_(self._local_monitor)
            self._local_monitor = None
        if self._global_monitor:
            NSEvent.removeMonitor_(self._global_monitor)
            self._global_monitor = None
        if self._panel:
            self._panel.orderOut_(None)
            self._panel = None
            # Hide our app — macOS automatically reactivates the previous app
            NSApplication.sharedApplication().hide_(None)
        self._buttons = []
        self._formats = []
        self._callback = None
        self._ai_callback = None
        self._ai_mode = False
        self._ai_input = None
        self._ai_text_view = None
        self._blur_view = None
        self._loading = False
        self._loading_label = None
        self._field_action_target = None
        self._ai_text_delegate = None
        log.debug("Popup dismissed")

    def show_loading(self) -> None:
        """Replace AI sub-panel content with a loading indicator."""
        if not self._panel or not self._blur_view:
            return

        self._loading = True

        # Clear all subviews from blur_view and rebuild with loading state
        for subview in list(self._blur_view.subviews()):
            subview.removeFromSuperview()

        panel_height = self._panel.frame().size.height

        # Header
        header_y = panel_height - 36
        header = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, header_y, PANEL_WIDTH - PADDING_H * 2, 22)
        )
        header.setStringValue_("\U0001F9E0 Reformat with AI")
        header.setBezeled_(False)
        header.setDrawsBackground_(False)
        header.setEditable_(False)
        header.setSelectable_(False)
        header.setFont_(NSFont.systemFontOfSize_weight_(13, NSFontWeightSemibold))
        header.setTextColor_(_CLR_TEXT_SECONDARY)
        self._blur_view.addSubview_(header)

        # "Thinking..." label — centered in panel
        center_y = (panel_height - 24) / 2
        loading_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, center_y, PANEL_WIDTH - PADDING_H * 2, 24)
        )
        loading_label.setStringValue_("Thinking...")
        loading_label.setBezeled_(False)
        loading_label.setDrawsBackground_(False)
        loading_label.setEditable_(False)
        loading_label.setSelectable_(False)
        loading_label.setFont_(NSFont.systemFontOfSize_weight_(14, NSFontWeightMedium))
        loading_label.setTextColor_(_CLR_TEXT_PRIMARY)
        loading_label.setAlignment_(1)  # center
        self._blur_view.addSubview_(loading_label)
        self._loading_label = loading_label

        # Animated dots via timer
        self._dot_count = 0
        self._loading_timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            0.4, True, lambda _: self._animate_dots()
        )

        # Footer: Esc to cancel
        footer = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, 8, PANEL_WIDTH - PADDING_H * 2, 16)
        )
        footer.setStringValue_("Esc Cancel")
        footer.setBezeled_(False)
        footer.setDrawsBackground_(False)
        footer.setEditable_(False)
        footer.setSelectable_(False)
        footer.setFont_(NSFont.systemFontOfSize_(10.5))
        footer.setTextColor_(_CLR_TEXT_DIM)
        self._blur_view.addSubview_(footer)

    def _animate_dots(self) -> None:
        """Cycle the loading dots animation."""
        if self._loading_label:
            self._dot_count = (self._dot_count + 1) % 4
            dots = "." * self._dot_count
            self._loading_label.setStringValue_(f"Thinking{dots}")

    def _stop_loading_animation(self) -> None:
        """Stop the loading dots timer."""
        if self._loading_timer:
            self._loading_timer.invalidate()
            self._loading_timer = None

    def _show_ai_panel(self) -> None:
        """Transition popup to AI sub-panel: text input + preset chips.

        Replaces the current panel with a new _AIPanel that handles Esc via
        sendEvent_ override — no local event monitor needed, so the text field
        receives all keystrokes directly.
        """
        if not self._panel:
            return

        # Clean up inline preview if open
        if self._preview_visible:
            self._preview_visible = False
            self._preview_animating = False
            if self._preview_webview:
                self._preview_webview.removeFromSuperview()
                self._preview_webview = None
            if self._preview_title_bar:
                self._preview_title_bar.removeFromSuperview()
                self._preview_title_bar = None
            if self._preview_separator:
                self._preview_separator.removeFromSuperview()
                self._preview_separator = None
            self._preview_copy_btn = None

        self._ai_mode = True
        self._transitioning = True

        # --- Remove the local event monitor entirely.
        # The _AIPanel subclass handles Esc via sendEvent_ override,
        # and Enter is handled by the text field's action target.
        # This ensures the NSTextField's field editor gets ALL keystrokes. ---
        if self._local_monitor:
            NSEvent.removeMonitor_(self._local_monitor)
            self._local_monitor = None

        # Close the old panel and create a new _AIPanel
        old_frame = self._panel.frame()
        self._panel.orderOut_(None)

        # Calculate panel height dynamically based on preset count
        presets = get_ai_presets()
        input_h = 36
        footer_h = 32
        ai_panel_height = input_h + 1 + len(presets) * ROW_HEIGHT + footer_h + 8
        ai_panel_height = max(ai_panel_height, 200)  # minimum height

        delta = ai_panel_height - old_frame.size.height
        new_frame = NSMakeRect(old_frame.origin.x, old_frame.origin.y - delta,
                               PANEL_WIDTH, ai_panel_height)

        panel = _AIPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            new_frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        panel._esc_callback = self.dismiss
        panel.setLevel_(NSFloatingWindowLevel + 1)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setMovableByWindowBackground_(False)
        panel.setBecomesKeyOnlyIfNeeded_(False)
        panel.setCollectionBehavior_(1 << 0 | 1 << 3)

        dark_appearance = NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark")
        panel.setAppearance_(dark_appearance)

        # Blur background
        blur_view = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PANEL_WIDTH, ai_panel_height)
        )
        blur_view.setMaterial_(9)
        blur_view.setBlendingMode_(0)
        blur_view.setState_(1)
        blur_view.setWantsLayer_(True)
        blur_view.layer().setCornerRadius_(CORNER_RADIUS)
        blur_view.layer().setMasksToBounds_(True)
        panel.contentView().addSubview_(blur_view)

        self._panel = panel
        self._blur_view = blur_view

        panel_h = ai_panel_height
        input_h = 36  # taller single-line input, command-palette style

        # === TOP: Text input flush at the top (command-palette search bar) ===
        input_y = panel_h - input_h
        input_w = PANEL_WIDTH

        # The text view sits at the very top of the panel, full width,
        # with internal padding via textContainerInset.
        text_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, input_w - 24, input_h)
        )
        text_view.setFont_(NSFont.systemFontOfSize_(14))
        text_view.setTextColor_(_CLR_TEXT_PRIMARY)
        text_view.setInsertionPointColor_(_CLR_TEXT_PRIMARY)
        text_view.setBackgroundColor_(NSColor.clearColor())
        text_view.setDrawsBackground_(False)
        text_view.setEditable_(True)
        text_view.setSelectable_(True)
        text_view.setRichText_(False)
        text_view.setVerticallyResizable_(False)
        text_view.setHorizontallyResizable_(False)
        text_view.textContainer().setWidthTracksTextView_(True)
        # NSSize(width, height) — width=horizontal padding, height=vertical padding
        # Vertically center 17px line in 36px bar: (36 - 17) / 2 ≈ 9
        text_view.setTextContainerInset_((0, 9))

        scroll_view = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(12, input_y, input_w - 24, input_h)
        )
        scroll_view.setHasVerticalScroller_(False)
        scroll_view.setHasHorizontalScroller_(False)
        scroll_view.setDrawsBackground_(False)
        scroll_view.setBorderType_(0)  # NSNoBorder — seamless with panel
        scroll_view.setDocumentView_(text_view)
        blur_view.addSubview_(scroll_view)
        self._ai_text_view = text_view

        # Placeholder label (disappears when user types)
        # Align placeholder with the text view's text (12px scroll inset + ~5px text container)
        placeholder = NSTextField.alloc().initWithFrame_(
            NSMakeRect(17, input_y + 9, input_w - 32, 20)
        )
        placeholder.setStringValue_("Describe how to reformat...")
        placeholder.setBezeled_(False)
        placeholder.setDrawsBackground_(False)
        placeholder.setEditable_(False)
        placeholder.setSelectable_(False)
        placeholder.setFont_(NSFont.systemFontOfSize_(14))
        placeholder.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.28))
        blur_view.addSubview_(placeholder)
        self._ai_placeholder = placeholder

        # Delegate to hide placeholder when user types
        delegate = _AITextDelegate.alloc().init()
        delegate._placeholder = placeholder
        text_view.setDelegate_(delegate)
        self._ai_text_delegate = delegate  # prevent GC

        # Wire callbacks through the panel's sendEvent_ override
        panel._enter_callback = self._submit_ai_prompt
        panel._down_callback = self._ai_move_down
        panel._up_callback = self._ai_move_up
        self._ai_chips = []
        self._ai_selected_index = -1  # start in text input

        # === Separator below the input bar ===
        sep_y = input_y - 1
        sep = NSView.alloc().initWithFrame_(
            NSMakeRect(0, sep_y, PANEL_WIDTH, 1)
        )
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(_CLR_SEPARATOR.CGColor())
        blur_view.addSubview_(sep)

        # === Preset chips as rows (like command palette results) ===
        row_y = sep_y
        for preset in presets:
            row_y -= ROW_HEIGHT
            chip = _PresetChip.alloc_init(
                NSMakeRect(0, row_y, PANEL_WIDTH, ROW_HEIGHT),
                label=preset,
                on_click=self._on_preset_click,
            )
            blur_view.addSubview_(chip)
            self._ai_chips.append(chip)

        # === Footer ===
        footer = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, 8, PANEL_WIDTH - PADDING_H * 2, 16)
        )
        footer.setStringValue_("\u2191\u2193 Navigate    \u21A9 Send    Esc Cancel")
        footer.setBezeled_(False)
        footer.setDrawsBackground_(False)
        footer.setEditable_(False)
        footer.setSelectable_(False)
        footer.setFont_(NSFont.systemFontOfSize_(10.5))
        footer.setTextColor_(_CLR_TEXT_DIM)
        blur_view.addSubview_(footer)

        # Show the new panel and activate app
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel.setAlphaValue_(1.0)
        panel.makeKeyAndOrderFront_(None)
        panel.makeKeyWindow()

        # Focus the text view — defer to next run loop so layout completes
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            0.05, False, lambda _: self._focus_ai_input()
        )
        # Clear transition guard after a short delay
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            0.2, False, lambda _: setattr(self, '_transitioning', False)
        )

        log.debug("AI sub-panel shown (using _AIPanel + NSTextView, no event monitor)")

    def _focus_ai_input(self) -> None:
        """Deferred focus setter for the AI text view."""
        if self._panel and self._ai_text_view:
            self._panel.makeKeyWindow()
            self._panel.makeFirstResponder_(self._ai_text_view)
            fr = self._panel.firstResponder()
            log.debug("AI focus: firstResponder is %s, isKey=%s",
                      fr.className() if fr else "None",
                      self._panel.isKeyWindow())

    def _ai_move_down(self) -> None:
        """Move selection down in AI preset list."""
        old = self._ai_selected_index
        new = old + 1
        if new >= len(self._ai_chips):
            return  # already at bottom
        # Deselect old
        if old >= 0 and old < len(self._ai_chips):
            self._ai_chips[old].setSelected_(False)
        # Select new
        self._ai_selected_index = new
        self._ai_chips[new].setSelected_(True)

    def _ai_move_up(self) -> None:
        """Move selection up in AI preset list, or back to text input."""
        old = self._ai_selected_index
        if old <= -1:
            return  # already in text input
        # Deselect old
        if old < len(self._ai_chips):
            self._ai_chips[old].setSelected_(False)
        new = old - 1
        self._ai_selected_index = new
        # new == -1 means back to text input (no preset highlighted)
        if new >= 0:
            self._ai_chips[new].setSelected_(True)

    def _on_preset_click(self, preset_text: str) -> None:
        """Handle click on a preset chip — fill input and submit."""
        if self._ai_text_view:
            self._ai_text_view.setString_(preset_text)
        self._submit_ai_prompt(preset_text)

    def _submit_ai_prompt(self, prompt: str | None = None) -> None:
        """Submit the AI rephrase request."""
        # If a preset row is selected via keyboard, use that
        if prompt is None and 0 <= self._ai_selected_index < len(self._ai_chips):
            prompt = self._ai_chips[self._ai_selected_index]._label
        # Otherwise use text input
        if prompt is None and self._ai_text_view:
            prompt = str(self._ai_text_view.string()).strip()

        if not prompt:
            return

        log.info("AI prompt submitted: %r", prompt)
        if self._ai_callback:
            self._ai_callback(prompt)

    def _on_button_click(self, index: int) -> None:
        """Handle click/key selection of a format."""
        if 0 <= index < len(self._formats):
            fmt = self._formats[index]

            # AI rephrase opens sub-panel instead of dismissing
            # Defer to next run loop so mouseDown_ finishes before we rebuild views
            if fmt == TargetFormat.AI_REPHRASE:
                NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                    0.0, False, lambda _: self._show_ai_panel()
                )
                return

            cb = self._callback
            self.dismiss()
            if cb:
                cb(fmt)

    def _handle_global_click(self, event) -> None:
        """Dismiss popup when user clicks outside it."""
        if self._loading or self._transitioning or self._preview_animating:
            return
        if self._preview and self._preview.is_visible:
            return
        self.dismiss()

    def _handle_key_event(self, event) -> object:
        """Handle keyboard navigation (normal mode — format list)."""
        if self._panel is None:
            return event

        keycode = event.keyCode()

        # Esc (53) — if preview open, collapse first; second Esc dismisses popup
        if keycode == 53:
            if self._preview_visible:
                self._toggle_preview()
                return None
            self.dismiss()
            return None

        # C (8) bare — if preview visible, copy all text
        if keycode == 8 and self._preview_visible:
            flags = event.modifierFlags()
            cmd_held = bool(flags & (1 << 20))
            if not cmd_held:
                self._on_preview_copy()
                return None

        # Down arrow (125)
        if keycode == 125:
            self._move_selection(1)
            return None

        # Up arrow (126)
        if keycode == 126:
            self._move_selection(-1)
            return None

        # Return/Enter (36)
        if keycode == 36:
            self._on_button_click(self._selected_index)
            return None

        # Number keys 1-6 for quick pick (keycodes 18-23 map to 1-6)
        number_keycodes = {18: 0, 19: 1, 20: 2, 21: 3, 23: 4, 22: 5}  # 1,2,3,4,5,6
        if keycode in number_keycodes:
            idx = number_keycodes[keycode]
            if idx < len(self._formats):
                self._on_button_click(idx)
                return None

        # Tab (48) — move down like arrow
        if keycode == 48:
            self._move_selection(1)
            return None

        # A (0) — open AI panel directly
        if keycode == 0:
            for i, fmt in enumerate(self._formats):
                if fmt == TargetFormat.AI_REPHRASE:
                    self._on_button_click(i)
                    return None
            return event

        # P (35) — toggle inline preview
        if keycode == 35 and self._clipboard_text:
            self._toggle_preview()
            return None

        return event

    def _toggle_preview(self) -> None:
        """Toggle the inline preview section."""
        if self._preview_animating:
            return
        if self._preview_visible:
            self._collapse_preview()
        else:
            self._expand_preview()

    def _expand_preview(self) -> None:
        """Expand inline preview section below the format list."""
        if not self._panel or not self._blur_view or self._preview_visible:
            return

        self._preview_animating = True
        self._preview_visible = True

        base_h = self._base_panel_height
        new_height = base_h + PREVIEW_TOTAL_HEIGHT

        # Screen bounds check — if expanding would push below screen, shift up
        panel_frame = self._panel.frame()
        screen = NSScreen.mainScreen()
        screen_bottom = screen.frame().origin.y
        new_origin_y = panel_frame.origin.y - PREVIEW_TOTAL_HEIGHT
        if new_origin_y < screen_bottom:
            new_origin_y = screen_bottom

        # Shift all existing subviews up by PREVIEW_TOTAL_HEIGHT (macOS bottom-left coords)
        for subview in list(self._blur_view.subviews()):
            f = subview.frame()
            subview.setFrame_(NSMakeRect(f.origin.x, f.origin.y + PREVIEW_TOTAL_HEIGHT,
                                         f.size.width, f.size.height))

        # Resize blur view
        self._blur_view.setFrame_(NSMakeRect(0, 0, PANEL_WIDTH, new_height))

        # --- Separator at boundary ---
        sep_y = PREVIEW_TOTAL_HEIGHT - 1
        sep = NSView.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, sep_y, PANEL_WIDTH - PADDING_H * 2, 1)
        )
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(_CLR_SEPARATOR.CGColor())
        self._blur_view.addSubview_(sep)
        self._preview_separator = sep

        # --- Mini title bar (32px) with "Preview" label + Copy button ---
        title_bar_y = PREVIEW_SECTION_HEIGHT
        title_bar = NSView.alloc().initWithFrame_(
            NSMakeRect(0, title_bar_y, PANEL_WIDTH, PREVIEW_TITLE_HEIGHT)
        )
        self._blur_view.addSubview_(title_bar)
        self._preview_title_bar = title_bar

        title_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING_H, 6, 120, 20)
        )
        title_label.setStringValue_("Preview")
        title_label.setBezeled_(False)
        title_label.setDrawsBackground_(False)
        title_label.setEditable_(False)
        title_label.setSelectable_(False)
        title_label.setFont_(NSFont.systemFontOfSize_weight_(12, NSFontWeightMedium))
        title_label.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.50))
        title_bar.addSubview_(title_label)

        # Copy button in title bar
        copy_btn_w = 60
        copy_btn_h = 24
        copy_btn = _CopyButton.alloc_init(
            NSMakeRect(PANEL_WIDTH - copy_btn_w - 12, 4, copy_btn_w, copy_btn_h),
            on_click=self._on_preview_copy,
        )
        title_bar.addSubview_(copy_btn)
        self._preview_copy_btn = copy_btn

        # --- WKWebView for rendered content ---
        webview_frame = NSMakeRect(6, 6, PANEL_WIDTH - 12, PREVIEW_SECTION_HEIGHT - 8)
        config = WKWebViewConfiguration.alloc().init()
        webview = WKWebView.alloc().initWithFrame_configuration_(webview_frame, config)
        webview.setWantsLayer_(True)
        webview.layer().setCornerRadius_(8)
        webview.layer().setMasksToBounds_(True)
        webview.setValue_forKey_(False, "drawsBackground")

        html = _render_to_html(self._clipboard_text)
        webview.loadHTMLString_baseURL_(html, None)
        self._blur_view.addSubview_(webview)
        self._preview_webview = webview
        self._preview_loaded_text = self._clipboard_text

        # Update footer hints
        if self._footer_field:
            self._footer_field.setStringValue_("P Close preview    C Copy    \u2191\u2193 Navigate    Esc Close")

        # Animate panel frame change
        new_frame = NSMakeRect(panel_frame.origin.x, new_origin_y,
                               PANEL_WIDTH, new_height)
        NSAnimationContext.beginGrouping()
        ctx = NSAnimationContext.currentContext()
        ctx.setDuration_(0.15)
        ctx.setCompletionHandler_(lambda: setattr(self, '_preview_animating', False))
        self._panel.animator().setFrame_display_(new_frame, True)
        NSAnimationContext.endGrouping()

        log.debug("Inline preview expanded")

    def _collapse_preview(self) -> None:
        """Collapse the inline preview section."""
        if not self._panel or not self._blur_view or not self._preview_visible:
            return

        self._preview_animating = True
        self._preview_visible = False

        # Remove preview subviews
        if self._preview_webview:
            self._preview_webview.removeFromSuperview()
            self._preview_webview = None
        if self._preview_title_bar:
            self._preview_title_bar.removeFromSuperview()
            self._preview_title_bar = None
        if self._preview_separator:
            self._preview_separator.removeFromSuperview()
            self._preview_separator = None
        self._preview_copy_btn = None

        # Shift existing subviews back down
        for subview in list(self._blur_view.subviews()):
            f = subview.frame()
            subview.setFrame_(NSMakeRect(f.origin.x, f.origin.y - PREVIEW_TOTAL_HEIGHT,
                                         f.size.width, f.size.height))

        # Resize blur view back
        base_h = self._base_panel_height
        self._blur_view.setFrame_(NSMakeRect(0, 0, PANEL_WIDTH, base_h))

        # Restore footer hints
        if self._footer_field:
            self._footer_field.setStringValue_("\u2191\u2193 Navigate    \u21A9 Select    P Preview    A AI    Esc Cancel")

        # Animate panel frame back
        panel_frame = self._panel.frame()
        restored_y = panel_frame.origin.y + PREVIEW_TOTAL_HEIGHT
        new_frame = NSMakeRect(panel_frame.origin.x, restored_y,
                               PANEL_WIDTH, base_h)
        NSAnimationContext.beginGrouping()
        ctx = NSAnimationContext.currentContext()
        ctx.setDuration_(0.15)
        ctx.setCompletionHandler_(lambda: setattr(self, '_preview_animating', False))
        self._panel.animator().setFrame_display_(new_frame, True)
        NSAnimationContext.endGrouping()

        log.debug("Inline preview collapsed")

    def _on_preview_copy(self) -> None:
        """Copy clipboard text and show feedback on the preview copy button."""
        from smartpaste.clipboard import write_clipboard
        write_clipboard(plain=self._clipboard_text)
        if self._preview_copy_btn:
            self._preview_copy_btn.show_copied_feedback()
        log.info("Inline preview: text copied to clipboard")

    def _move_selection(self, delta: int) -> None:
        """Move the selection highlight by delta rows."""
        if not self._buttons:
            return
        old = self._selected_index
        new = max(0, min(len(self._buttons) - 1, old + delta))
        if new != old:
            self._buttons[old].setSelected_(False)
            self._buttons[new].setSelected_(True)
            self._selected_index = new


# Toast icon constants
TOAST_ICON_SUCCESS = "\u2705"  # checkmark
TOAST_ICON_WARNING = "\u26A0\uFE0F"   # warning
TOAST_ICON_INFO = "\u2139\uFE0F"      # info

TOAST_WIDTH = 300
TOAST_HEIGHT = 40


class Toast:
    """Lightweight in-app toast notification — floating pill that auto-dismisses."""

    def __init__(self):
        self._panel: NSPanel | None = None
        self._timer = None

    def show(self, message: str, icon: str = TOAST_ICON_INFO, duration: float = 1.5) -> None:
        """Show a brief toast message, auto-dismisses after duration seconds."""
        _init_colors()
        self._dismiss_immediate()

        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = sf.origin.x + (sf.size.width - TOAST_WIDTH) / 2
        y = sf.origin.y + sf.size.height * 0.55

        frame = NSMakeRect(x, y, TOAST_WIDTH, TOAST_HEIGHT)

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSFloatingWindowLevel + 2)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setMovableByWindowBackground_(False)
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)  # stay visible even when app deactivates
        panel.setCollectionBehavior_(1 << 0 | 1 << 3)  # canJoinAllSpaces | transient

        dark = NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark")
        panel.setAppearance_(dark)

        # Blur background pill
        blur = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, TOAST_WIDTH, TOAST_HEIGHT)
        )
        blur.setMaterial_(9)  # HUDWindow
        blur.setBlendingMode_(0)
        blur.setState_(1)
        blur.setWantsLayer_(True)
        blur.layer().setCornerRadius_(TOAST_HEIGHT / 2)
        blur.layer().setMasksToBounds_(True)
        panel.contentView().addSubview_(blur)

        # Icon
        icon_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(14, (TOAST_HEIGHT - 20) / 2, 24, 20)
        )
        icon_field.setStringValue_(icon)
        icon_field.setBezeled_(False)
        icon_field.setDrawsBackground_(False)
        icon_field.setEditable_(False)
        icon_field.setSelectable_(False)
        icon_field.setFont_(NSFont.systemFontOfSize_(14))
        blur.addSubview_(icon_field)

        # Message
        msg_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(42, (TOAST_HEIGHT - 18) / 2, TOAST_WIDTH - 56, 18)
        )
        msg_field.setStringValue_(message)
        msg_field.setBezeled_(False)
        msg_field.setDrawsBackground_(False)
        msg_field.setEditable_(False)
        msg_field.setSelectable_(False)
        msg_field.setFont_(NSFont.systemFontOfSize_weight_(13, NSFontWeightMedium))
        msg_field.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.88))
        blur.addSubview_(msg_field)

        self._panel = panel

        # Unhide the app so the panel can appear (NSApp.hide_ may have run)
        NSApplication.sharedApplication().unhide_(None)

        # Fade in
        panel.setAlphaValue_(0.0)
        panel.orderFrontRegardless()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.15)
        panel.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

        # Schedule auto-dismiss
        self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            duration, False, lambda _: self._fade_out()
        )

    def _fade_out(self) -> None:
        """Fade out and remove the toast."""
        if self._panel:
            NSAnimationContext.beginGrouping()
            ctx = NSAnimationContext.currentContext()
            ctx.setDuration_(0.3)
            ctx.setCompletionHandler_(lambda: self._dismiss_immediate())
            self._panel.animator().setAlphaValue_(0.0)
            NSAnimationContext.endGrouping()

    def _dismiss_immediate(self) -> None:
        """Remove toast immediately."""
        if self._timer:
            self._timer.invalidate()
            self._timer = None
        if self._panel:
            self._panel.orderOut_(None)
            self._panel = None
            # Re-hide the app so focus stays with the previous app
            NSApplication.sharedApplication().hide_(None)
