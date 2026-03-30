"""Content type detection via regex heuristics for SmartPaste."""

import re

from smartpaste.constants import ContentType

# Tab-separated values detection (Google Sheets, Excel copy)
_TAB_RE = re.compile(r"\t")


def _is_terminal(text: str) -> bool:
    """Detect text copied from a terminal emulator.

    Terminal copies have distinctive artifacts:
    - Lines padded with trailing whitespace to the terminal column width
    - Many lines at roughly the same length
    - Soft-wrapped lines (long text broken at terminal width)
    """
    lines = text.split("\n")
    non_empty = [l for l in lines if l.strip()]
    if len(non_empty) < 2:
        return False

    # Count lines with significant trailing whitespace (10+ spaces)
    trailing_padded = sum(
        1 for l in non_empty
        if len(l) > len(l.rstrip()) and len(l) - len(l.rstrip()) > 10
    )

    # If >30% of non-empty lines have heavy trailing padding → terminal
    ratio = trailing_padded / len(non_empty)
    return ratio > 0.3


def _is_tsv(text: str) -> bool:
    """Detect tab-separated tabular data (copied from spreadsheets).

    Heuristic: at least 2 rows with tabs, and consistent column count.
    """
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    tab_counts = [l.count("\t") for l in lines]
    # Every line must have at least one tab
    if any(c == 0 for c in tab_counts):
        return False
    # Column count should be consistent (allow ±1 for trailing tabs)
    median = sorted(tab_counts)[len(tab_counts) // 2]
    return all(abs(c - median) <= 1 for c in tab_counts)


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

    # Terminal text — padded lines with trailing whitespace
    if _is_terminal(text):
        return ContentType.TERMINAL

    # TSV — spreadsheet data copied from Google Sheets / Excel
    if _is_tsv(text):
        return ContentType.TABLE

    # Box-drawing tables (CLI tool output) → treat as MARKDOWN
    # (preprocessing converts them to pipe tables before converters run)
    from smartpaste.converters.box_table import has_box_drawing
    if has_box_drawing(text):
        return ContentType.MARKDOWN

    md_score = sum(1 for p in _MD_PATTERNS if p.search(text))
    if md_score >= _MD_THRESHOLD:
        return ContentType.MARKDOWN

    code_score = sum(1 for p in _CODE_PATTERNS if p.search(text))
    if code_score >= _CODE_THRESHOLD:
        return ContentType.CODE

    return ContentType.PLAIN_TEXT
