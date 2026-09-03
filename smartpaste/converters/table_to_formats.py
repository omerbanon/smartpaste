"""Table (tab/comma/semicolon-separated) → target format converters for SmartPaste.

Handles content copied from Google Sheets, Excel, Numbers, CSV files, etc.
"""

import html as html_mod

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register
from smartpaste.converters.tabular import (
    parse_table,
    rows_to_aligned_text,
    rows_to_html_table,
)

_TABLE_CSS = (
    "<style>"
    "table { border-collapse: collapse; font-family: -apple-system, sans-serif; font-size: 14px; }"
    "th, td { border: 1px solid #ddd; padding: 6px 12px; text-align: left; }"
    "th { background: #f5f5f5; font-weight: 600; }"
    "tr:nth-child(even) td { background: #fafafa; }"
    "</style>"
)


def _html_table(text: str) -> str:
    rows = parse_table(text)
    return rows_to_html_table(rows, _TABLE_CSS) if rows else html_mod.escape(text)


def code_block(text: str) -> dict[str, str | None]:
    """Slack pastes <pre> as a code block, which keeps monospace alignment."""
    return {
        "html": f"<pre>{html_mod.escape(text)}</pre>",
        "plain": f"```\n{text}\n```",
    }


@register(ContentType.TABLE, TargetFormat.GOOGLE_DOCS)
def table_to_google_docs(text: str) -> dict[str, str | None]:
    return {"html": _html_table(text), "plain": text}


@register(ContentType.TABLE, TargetFormat.GMAIL)
def table_to_gmail(text: str) -> dict[str, str | None]:
    return {"html": _html_table(text), "plain": text}


@register(ContentType.TABLE, TargetFormat.SLACK)
def table_to_slack(text: str) -> dict[str, str | None]:
    # Slack has no tables; aligned monospace text in a code block is the closest.
    rows = parse_table(text)
    return code_block(rows_to_aligned_text(rows) if rows else text)


@register(ContentType.TABLE, TargetFormat.PLAIN)
def table_to_plain(text: str) -> dict[str, str | None]:
    return {"html": None, "plain": text}
