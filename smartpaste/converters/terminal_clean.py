"""Terminal text cleaner for SmartPaste.

Cleans text copied from terminal emulators: strips trailing whitespace padding,
rejoins soft-wrapped lines, collapses excessive blank lines. Then converts
the cleaned text to the target format using the same logic as markdown converters.
"""

import re
from collections import Counter

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register
from smartpaste.converters.md_to_html import _md_to_html, _strip_html_tags
from smartpaste.converters.table_to_formats import code_block


def clean_terminal_text(text: str) -> str:
    """Remove terminal artifacts from copied text.

    1. Strip trailing whitespace from every line
    2. Detect terminal width and rejoin soft-wrapped lines
    3. Collapse excessive blank lines
    """
    lines = text.split("\n")

    # Step 1: strip trailing whitespace
    lines = [l.rstrip() for l in lines]

    # Step 2: detect terminal width (most common length among longer lines)
    lengths = [len(l) for l in lines if len(l) > 40]
    term_width = 0
    if lengths:
        counts = Counter(lengths)
        # Terminal width is typically the most common long-line length
        term_width = counts.most_common(1)[0][0]

    # Step 3: rejoin soft-wrapped lines
    if term_width > 0:
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # A line was soft-wrapped if:
            # - it's exactly terminal width (±2 chars)
            # - next line is non-empty and continues the text (indented or starts mid-sentence)
            while (
                i + 1 < len(lines)
                and abs(len(line.rstrip()) - term_width) <= 2
                and line.rstrip()  # current line is non-empty
                and lines[i + 1].strip()  # next line is non-empty
                and not _is_new_block(lines[i + 1])  # next line isn't a new block element
            ):
                i += 1
                next_line = lines[i].strip()
                # Join with a space (unless current line already ends with one)
                if line.endswith(" ") or line.endswith("-"):
                    line = line.rstrip() + next_line
                else:
                    line = line + " " + next_line
            result.append(line)
            i += 1
        lines = result

    # Step 4: collapse 3+ blank lines to 1
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _is_new_block(line: str) -> bool:
    """Check if a line starts a new block element (list item, heading, etc.)."""
    stripped = line.strip()
    if not stripped:
        return True
    # List items
    if re.match(r"^\s*[-*+]\s", line):
        return True
    if re.match(r"^\s*\d+\.\s", line):
        return True
    # Headings
    if stripped.startswith("#"):
        return True
    # Blockquotes
    if stripped.startswith(">"):
        return True
    # Code fences
    if stripped.startswith("```"):
        return True
    return False


@register(ContentType.TERMINAL, TargetFormat.GOOGLE_DOCS)
def terminal_to_google_docs(text: str) -> dict[str, str | None]:
    cleaned = clean_terminal_text(text)
    html = _md_to_html(cleaned)
    return {"html": html, "plain": _strip_html_tags(html)}


@register(ContentType.TERMINAL, TargetFormat.GMAIL)
def terminal_to_gmail(text: str) -> dict[str, str | None]:
    cleaned = clean_terminal_text(text)
    html = _md_to_html(cleaned)
    return {"html": html, "plain": _strip_html_tags(html)}


@register(ContentType.TERMINAL, TargetFormat.SLACK)
def terminal_to_slack(text: str) -> dict[str, str | None]:
    # Terminal output is not markdown: stray * or # must stay literal, and
    # column alignment only survives inside a monospace code block.
    return code_block(clean_terminal_text(text))


@register(ContentType.TERMINAL, TargetFormat.CLI)
def terminal_to_cli(text: str) -> dict[str, str | None]:
    cleaned = clean_terminal_text(text)
    # CLI: just the cleaned text, no formatting
    return {"html": None, "plain": cleaned}


@register(ContentType.TERMINAL, TargetFormat.PLAIN)
def terminal_to_plain(text: str) -> dict[str, str | None]:
    cleaned = clean_terminal_text(text)
    return {"html": None, "plain": cleaned}
