"""NSPasteboard read/write operations for SmartPaste."""

import logging

from AppKit import NSPasteboard, NSPasteboardTypeHTML, NSPasteboardTypeString

from smartpaste.constants import PASTEBOARD_TYPE_HTML, PASTEBOARD_TYPE_PLAIN

log = logging.getLogger(__name__)


def read_clipboard_string() -> str | None:
    """Read plain-text string from the system clipboard."""
    pb = NSPasteboard.generalPasteboard()
    text = pb.stringForType_(NSPasteboardTypeString)
    return str(text) if text else None


def read_clipboard_html() -> str | None:
    """Read HTML content from the system clipboard, if available."""
    pb = NSPasteboard.generalPasteboard()
    html = pb.stringForType_(NSPasteboardTypeHTML)
    return str(html) if html else None


def read_clipboard_types() -> list[str]:
    """Return list of pasteboard type strings currently on the clipboard."""
    pb = NSPasteboard.generalPasteboard()
    types = pb.types()
    return [str(t) for t in types] if types else []


def write_clipboard(*, html: str | None = None, plain: str | None = None) -> None:
    """Write content to the system clipboard.

    Writes both HTML and plain-text representations so that rich-text apps
    (Google Docs, Gmail, Slack Canvas) use HTML while others fall back to plain.
    """
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()

    types_to_declare = []
    if html:
        types_to_declare.append(PASTEBOARD_TYPE_HTML)
    if plain:
        types_to_declare.append(PASTEBOARD_TYPE_PLAIN)

    if not types_to_declare:
        log.warning("write_clipboard called with no content")
        return

    pb.declareTypes_owner_(types_to_declare, None)

    if html:
        pb.setString_forType_(html, PASTEBOARD_TYPE_HTML)
    if plain:
        pb.setString_forType_(plain, PASTEBOARD_TYPE_PLAIN)

    log.debug("Wrote to clipboard: html=%s, plain=%s", bool(html), bool(plain))
