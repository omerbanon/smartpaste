"""Content type detection via regex heuristics for SmartPaste."""

import re

from smartpaste.constants import ContentType

# Markdown signals — each pattern, if found, adds 1 to the score.
_MD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^#{1,6}\s+\S", re.MULTILINE),           # headings
    re.compile(r"\*\*[^*]+\*\*"),                          # bold
    re.compile(r"(?<!\*)\*[^*]+\*(?!\*)"),                 # italic (single *)
    re.compile(r"_[^_]+_"),                                # italic (underscores)
    re.compile(r"^[-*+]\s+\S", re.MULTILINE),             # unordered list
    re.compile(r"^\d+\.\s+\S", re.MULTILINE),             # ordered list
    re.compile(r"\[.+?\]\(.+?\)"),                         # links
    re.compile(r"!\[.*?\]\(.+?\)"),                        # images
    re.compile(r"^>\s+\S", re.MULTILINE),                  # blockquote
    re.compile(r"`[^`]+`"),                                # inline code
    re.compile(r"^```", re.MULTILINE),                     # fenced code block
    re.compile(r"^\|.+\|.+\|", re.MULTILINE),             # table rows
    re.compile(r"^---+$", re.MULTILINE),                   # horizontal rule
    re.compile(r"~~[^~]+~~"),                              # strikethrough
]

# Code signals — fenced blocks, common syntax patterns
_CODE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^```\w+", re.MULTILINE),                  # fenced with language
    re.compile(r"^(def |class |import |from .+ import )", re.MULTILINE),  # Python
    re.compile(r"^(function |const |let |var |=>)", re.MULTILINE),        # JS
    re.compile(r"[{}\[\];]"),                               # braces / semicolons
    re.compile(r"^\s{4,}\S", re.MULTILINE),                # 4+ space indentation
]

_MD_THRESHOLD = 2
_CODE_THRESHOLD = 3


def detect(text: str) -> ContentType:
    """Classify clipboard text into a ContentType.

    Scoring:
    - Count how many distinct markdown patterns match. >=2 → MARKDOWN.
    - If not markdown, count code patterns. >=3 → CODE.
    - Else → PLAIN_TEXT.

    Image detection is handled separately (by checking pasteboard types),
    not in this text-based detector.
    """
    if not text or not text.strip():
        return ContentType.PLAIN_TEXT

    md_score = sum(1 for p in _MD_PATTERNS if p.search(text))
    if md_score >= _MD_THRESHOLD:
        return ContentType.MARKDOWN

    code_score = sum(1 for p in _CODE_PATTERNS if p.search(text))
    if code_score >= _CODE_THRESHOLD:
        return ContentType.CODE

    return ContentType.PLAIN_TEXT
