"""TSV (tab-separated) table → various format converters for SmartPaste.

Handles content copied from Google Sheets, Excel, Numbers, etc.
"""

import html as html_mod

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register


def _parse_tsv(text: str) -> list[list[str]]:
    """Parse tab-separated text into a 2D list of cell values."""
    lines = text.strip().splitlines()
    return [line.split("\t") for line in lines if line.strip()]


def _tsv_to_html_table(text: str) -> str:
    """Convert TSV to an HTML table with light styling for rich-text apps."""
    rows = _parse_tsv(text)
    if not rows:
        return ""

    css = (
        "<style>"
        "table { border-collapse: collapse; font-family: -apple-system, sans-serif; font-size: 14px; }"
        "th, td { border: 1px solid #ddd; padding: 6px 12px; text-align: left; }"
        "th { background: #f5f5f5; font-weight: 600; }"
        "tr:nth-child(even) td { background: #fafafa; }"
        "</style>"
    )

    parts = [css, "<table>"]

    # First row as header
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
    return "".join(parts)


def _tsv_to_md_table(text: str) -> str:
    """Convert TSV to a markdown table."""
    rows = _parse_tsv(text)
    if not rows:
        return text

    # Calculate max column widths for alignment
    max_cols = max(len(r) for r in rows)
    # Pad rows to have equal columns
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    widths = [max(len(r[i]) for r in rows) for i in range(max_cols)]
    widths = [max(w, 3) for w in widths]  # minimum 3 for separator

    lines = []
    # Header
    header = "| " + " | ".join(rows[0][i].ljust(widths[i]) for i in range(max_cols)) + " |"
    lines.append(header)
    # Separator
    sep = "| " + " | ".join("-" * widths[i] for i in range(max_cols)) + " |"
    lines.append(sep)
    # Data rows
    for row in rows[1:]:
        line = "| " + " | ".join(row[i].ljust(widths[i]) for i in range(max_cols)) + " |"
        lines.append(line)

    return "\n".join(lines)



@register(ContentType.TABLE, TargetFormat.GOOGLE_DOCS)
def table_to_google_docs(text: str) -> dict[str, str | None]:
    html = _tsv_to_html_table(text)
    return {"html": html, "plain": text}


@register(ContentType.TABLE, TargetFormat.GMAIL)
def table_to_gmail(text: str) -> dict[str, str | None]:
    html = _tsv_to_html_table(text)
    return {"html": html, "plain": text}


@register(ContentType.TABLE, TargetFormat.SLACK)
def table_to_slack(text: str) -> dict[str, str | None]:
    # Slack's rich text editor reads HTML tables from clipboard
    html = _tsv_to_html_table(text)
    return {"html": html, "plain": text}


@register(ContentType.TABLE, TargetFormat.PLAIN)
def table_to_plain(text: str) -> dict[str, str | None]:
    return {"html": None, "plain": text}
