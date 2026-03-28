"""Enums and pasteboard type constants for SmartPaste."""

from enum import Enum, auto


class ContentType(Enum):
    MARKDOWN = auto()
    CODE = auto()
    PLAIN_TEXT = auto()
    IMAGE = auto()


class TargetFormat(Enum):
    GOOGLE_DOCS = "Google Docs"
    GMAIL = "Gmail"
    SLACK = "Slack"
    NOTION = "Notion"
    CLI = "CLI (Compact)"
    PLAIN = "Plain Text"


# NSPasteboard type strings
PASTEBOARD_TYPE_HTML = "public.html"
PASTEBOARD_TYPE_PLAIN = "public.utf8-plain-text"
PASTEBOARD_TYPE_RTF = "public.rtf"
PASTEBOARD_TYPE_PNG = "public.png"
PASTEBOARD_TYPE_TIFF = "public.tiff"

# Maps ContentType → list of TargetFormats shown in the popup
FORMAT_OPTIONS: dict[ContentType, list[TargetFormat]] = {
    ContentType.MARKDOWN: [
        TargetFormat.GOOGLE_DOCS,
        TargetFormat.GMAIL,
        TargetFormat.SLACK,
        TargetFormat.NOTION,
        TargetFormat.CLI,
        TargetFormat.PLAIN,
    ],
    ContentType.CODE: [
        TargetFormat.GOOGLE_DOCS,
        TargetFormat.SLACK,
        TargetFormat.CLI,
        TargetFormat.PLAIN,
    ],
    ContentType.PLAIN_TEXT: [
        TargetFormat.CLI,
        TargetFormat.PLAIN,
    ],
}

# Display labels for content types
CONTENT_TYPE_LABELS: dict[ContentType, str] = {
    ContentType.MARKDOWN: "Markdown Detected",
    ContentType.CODE: "Code Detected",
    ContentType.PLAIN_TEXT: "Plain Text",
    ContentType.IMAGE: "Image Detected",
}
