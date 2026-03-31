"""Rich text preview panel for SmartPaste.

Renders clipboard markdown as formatted HTML in a dark WKWebView panel.
Triggered by pressing "P" while the format popup is open.
"""

import html as html_mod
import json
import logging
import re

import markdown as md
from AppKit import (
    NSAnimationContext,
    NSApplication,
    NSAppearance,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSFont,
    NSFontWeightMedium,
    NSFontWeightSemibold,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSTextField,
    NSTimer,
    NSView,
    NSVisualEffectView,
    NSWindowStyleMaskBorderless,
)
from WebKit import WKWebView, WKWebViewConfiguration

from smartpaste.clipboard import write_clipboard

log = logging.getLogger(__name__)

PREVIEW_WIDTH = 700
PREVIEW_HEIGHT = 560
CORNER_RADIUS = 12
TITLE_BAR_HEIGHT = 40
COPY_BTN_WIDTH = 72
COPY_BTN_HEIGHT = 28

_MD_EXTENSIONS = [
    "tables",
    "fenced_code",
    "nl2br",
    "sane_lists",
    "pymdownx.tilde",
]

_DARK_CSS = """
:root { color-scheme: dark; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
    font-size: 14px;
    line-height: 1.65;
    color: rgba(255, 255, 255, 0.88);
    background: transparent;
    padding: 20px 24px 24px;
    -webkit-font-smoothing: antialiased;
}
h1, h2, h3, h4, h5, h6 {
    color: rgba(255, 255, 255, 0.95);
    margin-top: 20px;
    margin-bottom: 8px;
    font-weight: 600;
    line-height: 1.3;
}
h1 { font-size: 22px; }
h2 { font-size: 18px; }
h3 { font-size: 16px; }
h4, h5, h6 { font-size: 14px; }
p { margin-bottom: 10px; }
strong { color: rgba(255, 255, 255, 0.95); font-weight: 600; }
em { font-style: italic; }
del { opacity: 0.5; text-decoration: line-through; }
a { color: #6cb4ff; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
    font-family: 'SF Mono', Menlo, monospace;
    font-size: 12.5px;
    background: rgba(255, 255, 255, 0.08);
    padding: 2px 6px;
    border-radius: 4px;
    color: rgba(255, 255, 255, 0.82);
}
pre {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 14px 16px;
    margin: 12px 0;
    overflow-x: auto;
}
pre code {
    background: none;
    padding: 0;
    border-radius: 0;
    font-size: 12.5px;
    line-height: 1.5;
}
blockquote {
    border-left: 3px solid rgba(255, 255, 255, 0.2);
    padding-left: 14px;
    color: rgba(255, 255, 255, 0.6);
    margin: 10px 0;
}
ul, ol {
    padding-left: 22px;
    margin-bottom: 10px;
}
li { margin-bottom: 4px; }
table {
    border-collapse: collapse;
    margin: 12px 0;
    width: 100%;
    font-size: 13px;
}
th, td {
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 8px 12px;
    text-align: left;
}
th {
    background: rgba(255, 255, 255, 0.06);
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
}
tr:nth-child(even) td { background: rgba(255, 255, 255, 0.02); }
hr {
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    margin: 16px 0;
}
img { max-width: 100%; border-radius: 6px; }
::selection { background: rgba(100, 160, 255, 0.35); color: inherit; }
body { -webkit-user-select: text; cursor: text; }
"""


def _preprocess_for_preview(text: str) -> str:
    """Normalize text for better markdown rendering in the preview.

    Fixes common clipboard issues: missing blank lines before lists/headings,
    mixed line endings, etc.
    """
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    result: list[str] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Ensure blank line before headings (if previous line is non-empty text)
        if stripped.startswith("#") and i > 0 and result and result[-1].strip():
            result.append("")
        # Ensure blank line before list items starting a new list
        if i > 0 and result and result[-1].strip():
            if re.match(r"^\d+\.\s", stripped) or re.match(r"^[-*+]\s", stripped):
                # Check if previous line was NOT a list item (i.e. this is a list start)
                prev = result[-1].strip()
                if not re.match(r"^\d+\.\s", prev) and not re.match(r"^[-*+]\s", prev):
                    result.append("")
        result.append(line)

    return "\n".join(result)


def _is_tsv(text: str) -> bool:
    """Quick check if text is tab-separated table data."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    return all("\t" in l for l in lines)


def _render_tsv_to_html(text: str) -> str:
    """Convert tab-separated data to a dark-themed HTML table."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    rows = [l.split("\t") for l in lines]

    parts = ["<table>"]
    # Header row
    parts.append("<thead><tr>")
    for cell in rows[0]:
        parts.append(f"<th>{html_mod.escape(cell)}</th>")
    parts.append("</tr></thead>")
    # Data rows
    if len(rows) > 1:
        parts.append("<tbody>")
        for row in rows[1:]:
            parts.append("<tr>")
            for cell in row:
                parts.append(f"<td>{html_mod.escape(cell)}</td>")
            parts.append("</tr>")
        parts.append("</tbody>")
    parts.append("</table>")

    row_count = len(rows) - 1
    col_count = max(len(r) for r in rows)
    subtitle = f"<p style='color:rgba(255,255,255,0.4); font-size:12px; margin-top:12px;'>{row_count} rows \u00D7 {col_count} columns</p>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_DARK_CSS}</style></head>
<body>{"".join(parts)}{subtitle}</body>
</html>"""


def _is_json(text: str) -> bool:
    """Check if text is a JSON object or array."""
    stripped = text.strip()
    if not (stripped.startswith(("{", "[")) and stripped.endswith(("}", "]"))):
        return False
    try:
        json.loads(stripped)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


_JSON_CSS = """
:root { color-scheme: dark; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'SF Mono', Menlo, monospace;
    font-size: 13px;
    line-height: 1.6;
    color: rgba(255, 255, 255, 0.88);
    background: transparent;
    padding: 16px 20px;
    -webkit-font-smoothing: antialiased;
}
.tree { list-style: none; padding-left: 0; }
.tree ul { list-style: none; padding-left: 20px; }
.toggle {
    cursor: pointer;
    user-select: none;
    display: inline-block;
    width: 16px;
    text-align: center;
    color: rgba(255,255,255,0.4);
    font-size: 11px;
}
.toggle:hover { color: rgba(255,255,255,0.8); }
.key { color: #c9a0ff; }
.str { color: #98c379; }
.num { color: #6cb4ff; }
.bool { color: #e5a63c; }
.null { color: rgba(255,255,255,0.4); }
.bracket { color: rgba(255,255,255,0.5); }
.badge {
    font-size: 11px;
    color: rgba(255,255,255,0.35);
    margin-left: 4px;
}
.comma { color: rgba(255,255,255,0.3); }
.hidden { display: none; }
li { white-space: nowrap; }
::selection { background: rgba(100, 160, 255, 0.35); color: inherit; }
body { -webkit-user-select: text; cursor: text; }
"""

_JSON_JS = """
function toggle(el) {
    var children = el.parentElement.querySelector('ul');
    var badge = el.parentElement.querySelector('.badge');
    if (!children) return;
    if (children.classList.contains('hidden')) {
        children.classList.remove('hidden');
        el.textContent = '\\u25BC';
        if (badge) badge.classList.add('hidden');
    } else {
        children.classList.add('hidden');
        el.textContent = '\\u25B6';
        if (badge) badge.classList.remove('hidden');
    }
}
"""


def _render_json_to_html(text: str) -> str:
    """Render JSON as a collapsible tree view."""
    data = json.loads(text.strip())

    def _val(v, depth=0):
        """Render a JSON value as HTML."""
        if isinstance(v, dict):
            return _obj(v, depth)
        if isinstance(v, list):
            return _arr(v, depth)
        if isinstance(v, str):
            return f'<span class="str">&quot;{html_mod.escape(v)}&quot;</span>'
        if isinstance(v, bool):
            return f'<span class="bool">{"true" if v else "false"}</span>'
        if v is None:
            return '<span class="null">null</span>'
        return f'<span class="num">{html_mod.escape(str(v))}</span>'

    def _obj(obj, depth=0):
        if not obj:
            return '<span class="bracket">{}</span>'
        collapsed = ' class="hidden"' if depth > 0 else ""
        badge_cls = ' class="badge"' if depth > 0 else ' class="badge hidden"'
        arrow = "▶" if depth > 0 else "▼"
        items = []
        keys = list(obj.keys())
        for i, k in enumerate(keys):
            comma = '<span class="comma">,</span>' if i < len(keys) - 1 else ""
            items.append(
                f'<li><span class="key">&quot;{html_mod.escape(k)}&quot;</span>: '
                f'{_val(obj[k], depth + 1)}{comma}</li>'
            )
        return (
            f'<span class="toggle" onclick="toggle(this)">{arrow}</span>'
            f'<span class="bracket">{{</span>'
            f'<span{badge_cls}>{{{len(obj)}}}</span>'
            f'<ul{collapsed}>{"".join(items)}</ul>'
            f'<span class="bracket">}}</span>'
        )

    def _arr(arr, depth=0):
        if not arr:
            return '<span class="bracket">[]</span>'
        collapsed = ' class="hidden"' if depth > 0 else ""
        badge_cls = ' class="badge"' if depth > 0 else ' class="badge hidden"'
        arrow = "▶" if depth > 0 else "▼"
        items = []
        for i, item in enumerate(arr):
            comma = '<span class="comma">,</span>' if i < len(arr) - 1 else ""
            items.append(f'<li>{_val(item, depth + 1)}{comma}</li>')
        return (
            f'<span class="toggle" onclick="toggle(this)">{arrow}</span>'
            f'<span class="bracket">[</span>'
            f'<span{badge_cls}>[{len(arr)}]</span>'
            f'<ul{collapsed}>{"".join(items)}</ul>'
            f'<span class="bracket">]</span>'
        )

    tree_html = f'<ul class="tree"><li>{_val(data, 0)}</li></ul>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>{_JSON_CSS}</style>
<script>{_JSON_JS}</script>
</head>
<body>{tree_html}</body>
</html>"""


def _render_md_to_html(text: str) -> str:
    """Convert markdown to a full HTML page with dark styling."""
    text = _preprocess_for_preview(text)
    body = md.markdown(text, extensions=_MD_EXTENSIONS)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_DARK_CSS}</style></head>
<body>{body}</body>
</html>"""


def _is_terminal(text: str) -> bool:
    """Quick check if text has terminal padding artifacts."""
    lines = text.split("\n")
    non_empty = [l for l in lines if l.strip()]
    if len(non_empty) < 2:
        return False
    trailing_padded = sum(
        1 for l in non_empty
        if len(l) > len(l.rstrip()) and len(l) - len(l.rstrip()) > 10
    )
    return trailing_padded / len(non_empty) > 0.3


def _render_to_html(text: str) -> str:
    """Pick the right renderer based on content type."""
    if _is_tsv(text):
        return _render_tsv_to_html(text)
    if _is_json(text):
        return _render_json_to_html(text)
    from smartpaste.converters.box_table import has_box_drawing, convert_box_tables_to_markdown
    if has_box_drawing(text):
        text = convert_box_tables_to_markdown(text)
    elif _is_terminal(text):
        from smartpaste.converters.terminal_clean import clean_terminal_text
        text = clean_terminal_text(text)
    return _render_md_to_html(text)


class _CopyButton(NSView):
    """Dark rounded 'Copy' button overlay."""

    @classmethod
    def alloc_init(cls, frame, on_click):
        self = cls.alloc().initWithFrame_(frame)
        self._on_click = on_click
        self._label = "Copy"

        self.setWantsLayer_(True)
        self.layer().setCornerRadius_(frame.size.height / 2)
        self.layer().setMasksToBounds_(True)

        # Label
        self._text_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, (frame.size.height - 16) / 2, frame.size.width, 16)
        )
        self._text_field.setStringValue_("Copy")
        self._text_field.setBezeled_(False)
        self._text_field.setDrawsBackground_(False)
        self._text_field.setEditable_(False)
        self._text_field.setSelectable_(False)
        self._text_field.setFont_(NSFont.systemFontOfSize_weight_(12, NSFontWeightSemibold))
        self._text_field.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.85))
        self._text_field.setAlignment_(1)  # center
        self.addSubview_(self._text_field)

        return self

    def drawRect_(self, rect):
        NSColor.colorWithWhite_alpha_(1.0, 0.12).set()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), self.bounds().size.height / 2, self.bounds().size.height / 2
        )
        path.fill()

    def mouseDown_(self, event):
        self._on_click()

    def show_copied_feedback(self):
        """Briefly change label to 'Copied!' then revert."""
        self._text_field.setStringValue_("\u2705 Copied!")
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0, False, lambda _: self._text_field.setStringValue_("Copy")
        )


class PreviewPanel:
    """Renders clipboard content as formatted rich text in a dark panel."""

    def __init__(self):
        self._panel: NSPanel | None = None
        self._monitor = None
        self._text: str = ""
        self._copy_btn: _CopyButton | None = None

    @property
    def is_visible(self) -> bool:
        return self._panel is not None

    def show(self, text: str) -> None:
        """Show the preview panel with rendered markdown content."""
        if self._panel:
            self.dismiss()

        self._text = text

        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = sf.origin.x + (sf.size.width - PREVIEW_WIDTH) / 2
        y = sf.origin.y + (sf.size.height - PREVIEW_HEIGHT) / 2 + 40

        frame = NSMakeRect(x, y, PREVIEW_WIDTH, PREVIEW_HEIGHT)

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSFloatingWindowLevel + 2)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setBecomesKeyOnlyIfNeeded_(False)
        panel.setCollectionBehavior_(1 << 0 | 1 << 3)

        dark = NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark")
        panel.setAppearance_(dark)

        # Blur background
        blur = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        )
        blur.setMaterial_(9)  # HUDWindow
        blur.setBlendingMode_(0)
        blur.setState_(1)
        blur.setWantsLayer_(True)
        blur.layer().setCornerRadius_(CORNER_RADIUS)
        blur.layer().setMasksToBounds_(True)
        panel.contentView().addSubview_(blur)

        # Title bar
        title_y = PREVIEW_HEIGHT - TITLE_BAR_HEIGHT
        title = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, title_y + 10, 200, 20)
        )
        title.setStringValue_("Preview")
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setEditable_(False)
        title.setSelectable_(False)
        title.setFont_(NSFont.systemFontOfSize_weight_(13, NSFontWeightMedium))
        title.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.55))
        blur.addSubview_(title)

        # Hint (shifted left to make room for Copy button)
        hint = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PREVIEW_WIDTH - 360, title_y + 10, 260, 20)
        )
        hint.setStringValue_("\u2318C Copy sel  \u00B7  C Copy all  \u00B7  Esc close")
        hint.setBezeled_(False)
        hint.setDrawsBackground_(False)
        hint.setEditable_(False)
        hint.setSelectable_(False)
        hint.setFont_(NSFont.systemFontOfSize_(11))
        hint.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.30))
        hint.setAlignment_(2)  # right
        blur.addSubview_(hint)

        # Copy button (top-right, in title bar)
        copy_btn = _CopyButton.alloc_init(
            NSMakeRect(
                PREVIEW_WIDTH - COPY_BTN_WIDTH - 16,
                title_y + 6,
                COPY_BTN_WIDTH,
                COPY_BTN_HEIGHT,
            ),
            on_click=self._on_copy,
        )
        blur.addSubview_(copy_btn)
        self._copy_btn = copy_btn

        # Separator
        sep = NSView.alloc().initWithFrame_(
            NSMakeRect(16, title_y, PREVIEW_WIDTH - 32, 1)
        )
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(
            NSColor.colorWithWhite_alpha_(1.0, 0.10).CGColor()
        )
        blur.addSubview_(sep)

        # WebView for rendered content
        webview_frame = NSMakeRect(8, 8, PREVIEW_WIDTH - 16, title_y - 12)
        config = WKWebViewConfiguration.alloc().init()
        webview = WKWebView.alloc().initWithFrame_configuration_(webview_frame, config)
        webview.setWantsLayer_(True)
        webview.layer().setCornerRadius_(8)
        webview.layer().setMasksToBounds_(True)
        # Make webview background transparent so blur shows through
        webview.setValue_forKey_(False, "drawsBackground")

        html = _render_to_html(text)
        webview.loadHTMLString_baseURL_(html, None)
        blur.addSubview_(webview)

        # Key monitor (Esc/P to close, C to copy)
        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            1 << 10,  # NSKeyDownMask
            self._handle_key,
        )

        self._panel = panel

        # Fade in
        panel.setAlphaValue_(0.0)
        panel.makeKeyAndOrderFront_(None)
        panel.makeKeyWindow()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.15)
        panel.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

        log.debug("Preview panel shown")

    def dismiss(self) -> None:
        """Close the preview panel."""
        if self._monitor:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        if self._panel:
            self._panel.orderOut_(None)
            self._panel = None
        self._copy_btn = None
        log.debug("Preview panel dismissed")

    def _on_copy(self) -> None:
        """Copy the original clipboard text."""
        write_clipboard(plain=self._text)
        if self._copy_btn:
            self._copy_btn.show_copied_feedback()
        log.info("Preview: text copied to clipboard")

    def _handle_key(self, event) -> object:
        """Esc (53) or P (35) to close, C (8) to copy all.

        Cmd+C passes through to WKWebView for copying selected text.
        Cmd+A passes through for select-all.
        """
        if self._panel is None:
            return event
        keycode = event.keyCode()
        flags = event.modifierFlags()
        cmd_held = bool(flags & (1 << 20))  # NSEventModifierFlagCommand

        # Let Cmd+C and Cmd+A pass through to webview (native copy / select-all)
        if cmd_held and keycode in (8, 0):  # Cmd+C, Cmd+A
            return event

        if keycode in (53, 35):  # Esc or P
            self.dismiss()
            return None
        if keycode == 8:  # bare C key → copy all
            self._on_copy()
            return None
        return event
