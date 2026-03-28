"""Command-palette style popup panel for SmartPaste.

Dark translucent panel with format options, keyboard navigation (Up/Down/1-5/Enter/Esc),
and mouse hover/click. Styled after VS Code / Raycast command palette.
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
    NSPanel,
    NSScreen,
    NSTextField,
    NSTrackingActiveAlways,
    NSTrackingArea,
    NSTrackingMouseEnteredAndExited,
    NSTrackingMouseMoved,
    NSView,
    NSVisualEffectView,
    NSWindowStyleMaskBorderless,
)
from AppKit import NSAppearance
from Foundation import NSObject

from smartpaste.constants import ContentType, TargetFormat, FORMAT_OPTIONS, CONTENT_TYPE_LABELS

log = logging.getLogger(__name__)

# Layout constants
PANEL_WIDTH = 480
ROW_HEIGHT = 44
ROW_INSET = 8        # horizontal inset for row highlight
ROW_PADDING = 6      # vertical padding inside rows
HEADER_HEIGHT = 52    # header area including padding
FOOTER_HEIGHT = 32    # bottom hint bar
CORNER_RADIUS = 12
PADDING_H = 16        # horizontal padding for text

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
    TargetFormat.NOTION: "\U0001F4D3",         # notebook
    TargetFormat.CLI: "\U0001F4BB",             # laptop (terminal)
    TargetFormat.PLAIN: "\U0001F4CB",          # clipboard
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


class FormatPopup:
    """Manages the command-palette style format selection panel."""

    def __init__(self):
        self._panel: NSPanel | None = None
        self._buttons: list[_FormatRow] = []
        self._selected_index: int = 0
        self._formats: list[TargetFormat] = []
        self._callback: Callable[[TargetFormat], None] | None = None
        self._local_monitor = None
        self._global_monitor = None

    def show(
        self,
        content_type: ContentType,
        on_select: Callable[[TargetFormat], None],
        char_count: int = 0,
    ) -> None:
        """Display the popup with format options for the given content type."""
        _init_colors()

        # Dismiss any existing popup first
        if self._panel:
            self.dismiss()

        self._formats = FORMAT_OPTIONS.get(content_type, [TargetFormat.PLAIN])
        self._callback = on_select
        self._selected_index = 0

        num_rows = len(self._formats)
        panel_height = HEADER_HEIGHT + num_rows * ROW_HEIGHT + FOOTER_HEIGHT + 12

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
        footer.setStringValue_("\u2191\u2193 Navigate    \u21A9 Select    Esc Cancel    1-5 Quick pick")
        footer.setBezeled_(False)
        footer.setDrawsBackground_(False)
        footer.setEditable_(False)
        footer.setSelectable_(False)
        footer.setFont_(NSFont.systemFontOfSize_(10.5))
        footer.setTextColor_(_CLR_TEXT_DIM)
        blur_view.addSubview_(footer)

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
        log.debug("Popup dismissed")

    def _on_button_click(self, index: int) -> None:
        """Handle click/key selection of a format."""
        if 0 <= index < len(self._formats):
            fmt = self._formats[index]
            cb = self._callback
            self.dismiss()
            if cb:
                cb(fmt)

    def _handle_global_click(self, event) -> None:
        """Dismiss popup when user clicks outside it."""
        self.dismiss()

    def _handle_key_event(self, event) -> object:
        """Handle keyboard navigation."""
        if self._panel is None:
            return event

        keycode = event.keyCode()

        # Esc (53)
        if keycode == 53:
            self.dismiss()
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

        # Number keys 1-5 for quick pick (keycodes 18-23 map to 1-6)
        number_keycodes = {18: 0, 19: 1, 20: 2, 21: 3, 23: 4}  # 1,2,3,4,5
        if keycode in number_keycodes:
            idx = number_keycodes[keycode]
            if idx < len(self._formats):
                self._on_button_click(idx)
                return None

        # Tab (48) — move down like arrow
        if keycode == 48:
            self._move_selection(1)
            return None

        return event

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
