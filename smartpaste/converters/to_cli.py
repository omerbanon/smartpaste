"""Compact/CLI converter — strips all unnecessary whitespace and formatting.

Keeps all real words intact. Removes:
- Extra spaces, tabs, trailing whitespace
- Blank lines (collapses to single newlines)
- Markdown formatting syntax (**, *, _, ~~, #, >, etc.)
- Markdown tables → compact "key: value" lines
- Leading/trailing whitespace per line
"""

import re

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register


def _table_to_compact(match: re.Match) -> str:
    """Convert a markdown table block into compact key:value lines.

    If 2 columns: "key: value" per row.
    If 3+ columns: comma-separated values per row.
    Strips separator rows (|---|---|).
    """
    block = match.group(0).strip()
    lines = block.split("\n")

    # Parse rows, skip separator rows
    rows: list[list[str]] = []
    for line in lines:
        # Skip separator rows like |---|---|
        if re.match(r"^\|[\s\-:|]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        cells = [c for c in cells if c]  # remove empty
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    headers = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []

    if not data_rows:
        # Header only — just join as a line
        return ", ".join(headers)

    result_lines = []
    if len(headers) == 2:
        # 2-column: "key: value" format
        for row in data_rows:
            if len(row) >= 2:
                result_lines.append(f"{row[0]}: {row[1]}")
            elif row:
                result_lines.append(row[0])
    else:
        # 3+ columns: header as context, each row comma-joined
        for row in data_rows:
            result_lines.append(", ".join(row))

    return "\n".join(result_lines)


def _compact(text: str) -> str:
    """Strip formatting and compress whitespace, keeping all real words."""
    result = text

    # Convert tables FIRST (before stripping pipes)
    result = re.sub(
        r"(?:^\|.+\|[ \t]*\n)+",
        _table_to_compact,
        result,
        flags=re.MULTILINE,
    )

    # Remove fenced code block markers (keep the code inside)
    result = re.sub(r"^```\w*\s*$", "", result, flags=re.MULTILINE)

    # Remove markdown heading markers
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)

    # Remove bold/italic markers
    result = re.sub(r"\*{1,3}([^*]+?)\*{1,3}", r"\1", result)
    result = re.sub(r"_{1,3}([^_]+?)_{1,3}", r"\1", result)

    # Remove strikethrough
    result = re.sub(r"~~([^~]+?)~~", r"\1", result)

    # Convert links [text](url) → text (url)
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", result)

    # Remove image syntax ![alt](url) → alt
    result = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", result)

    # Remove blockquote markers
    result = re.sub(r"^>\s*", "", result, flags=re.MULTILINE)

    # Remove horizontal rules
    result = re.sub(r"^[-*_]{3,}\s*$", "", result, flags=re.MULTILINE)

    # Remove inline code backticks (keep content)
    result = re.sub(r"`([^`]+)`", r"\1", result)

    # Strip trailing whitespace per line
    result = re.sub(r"[ \t]+$", "", result, flags=re.MULTILINE)

    # Collapse multiple spaces/tabs into single space
    result = re.sub(r"[ \t]+", " ", result)

    # Collapse 2+ blank lines into one
    result = re.sub(r"\n{3,}", "\n\n", result)

    # Strip leading whitespace per line
    result = re.sub(r"^[ \t]+", "", result, flags=re.MULTILINE)

    return result.strip()


@register(ContentType.MARKDOWN, TargetFormat.CLI)
def md_to_cli(text: str) -> dict[str, str | None]:
    return {"html": None, "plain": _compact(text)}


@register(ContentType.CODE, TargetFormat.CLI)
def code_to_cli(text: str) -> dict[str, str | None]:
    return {"html": None, "plain": _compact(text)}


@register(ContentType.PLAIN_TEXT, TargetFormat.CLI)
def plain_to_cli(text: str) -> dict[str, str | None]:
    return {"html": None, "plain": _compact(text)}
