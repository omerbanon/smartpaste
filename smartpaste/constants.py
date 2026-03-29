"""Enums and pasteboard type constants for SmartPaste."""

from enum import Enum, auto

from smartpaste.config import DEFAULT_PRESETS, load_config


class ContentType(Enum):
    MARKDOWN = auto()
    CODE = auto()
    TABLE = auto()
    TERMINAL = auto()
    PLAIN_TEXT = auto()
    IMAGE = auto()


class TargetFormat(Enum):
    GOOGLE_DOCS = "G-Doc / Confluence / Jira"
    GMAIL = "Gmail"
    SLACK = "Slack"
    CLI = "CLI (Compact)"
    PLAIN = "Plain Text"
    AI_REPHRASE = "Reformat with AI"


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
        TargetFormat.CLI,
        TargetFormat.PLAIN,
        TargetFormat.AI_REPHRASE,
    ],
    ContentType.CODE: [
        TargetFormat.GOOGLE_DOCS,
        TargetFormat.SLACK,
        TargetFormat.CLI,
        TargetFormat.PLAIN,
        TargetFormat.AI_REPHRASE,
    ],
    ContentType.TABLE: [
        TargetFormat.GOOGLE_DOCS,
        TargetFormat.GMAIL,
        TargetFormat.SLACK,
        TargetFormat.PLAIN,
        TargetFormat.AI_REPHRASE,
    ],
    ContentType.TERMINAL: [
        TargetFormat.GOOGLE_DOCS,
        TargetFormat.GMAIL,
        TargetFormat.SLACK,
        TargetFormat.CLI,
        TargetFormat.PLAIN,
        TargetFormat.AI_REPHRASE,
    ],
    ContentType.PLAIN_TEXT: [
        TargetFormat.AI_REPHRASE,
    ],
}

# AI rephrase preset prompts (kept as default reference)
DEFAULT_AI_PRESETS: list[str] = DEFAULT_PRESETS


def get_ai_presets() -> list[str]:
    """Return AI presets from config, falling back to defaults."""
    config = load_config()
    presets = config.get("presets")
    if presets and isinstance(presets, list):
        return presets
    return list(DEFAULT_PRESETS)

# Display labels for content types
CONTENT_TYPE_LABELS: dict[ContentType, str] = {
    ContentType.MARKDOWN: "Markdown Detected",
    ContentType.CODE: "Code Detected",
    ContentType.TABLE: "Table Detected",
    ContentType.TERMINAL: "Terminal Text Detected",
    ContentType.PLAIN_TEXT: "Plain Text",
    ContentType.IMAGE: "Image Detected",
}
