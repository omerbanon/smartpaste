"""Delimiter-separated table parsing shared by the detector, converters and preview.

Recognises tab-, comma- and semicolon-separated data (Sheets/Excel copies, CSV
files, CLI output) and renders rows as HTML, markdown, or monospace-aligned text.
"""

import csv
import html as html_mod
import io
import re

_DELIMITERS = ("\t", ",", ";")
_MD_BLOCK_RE = re.compile(r"^\s*([-*+]|\d+\.|#{1,6}|>)\s")
_MAX_CELL_LEN = 60  # longer cells read as prose, not data


def _non_empty_lines(text: str) -> list[str]:
    return [l for l in text.strip().splitlines() if l.strip()]


def _try_delimiter(lines: list[str], delim: str) -> list[list[str]] | None:
    """Parse *lines* with *delim*; return rows only if they look tabular."""
    if any(delim not in l for l in lines):
        return None
    try:
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delim))
    except csv.Error:
        return None
    rows = [[c.strip() for c in r] for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        return None
    counts = {len(r) for r in rows}
    if delim == "\t":
        # Spreadsheet copies may carry a trailing tab on some rows; allow ±1.
        if max(counts) - min(counts) > 1:
            return None
        width = max(counts)
        rows = [r + [""] * (width - len(r)) for r in rows]
    else:
        if len(counts) != 1 or min(counts) < 2:
            return None
        # Two commas in two sentences is prose, not a table. Quoted cells
        # are a CSV signal, so they get a pass.
        quoted = any('"' in l for l in lines)
        if len(rows[0]) == 2 and len(rows) < 3 and not quoted:
            return None
        if any(len(c) > _MAX_CELL_LEN for r in rows for c in r):
            return None
        # Cells that end like sentences are prose split on its commas.
        if any(c.endswith((".", "!", "?")) and " " in c for r in rows for c in r):
            return None
    return rows


def parse_table(text: str) -> list[list[str]] | None:
    """Return rows of cells if *text* is delimiter-separated data, else None.

    Tries tab first (most reliable), then comma, then semicolon.
    """
    lines = _non_empty_lines(text)
    if len(lines) < 2:
        return None
    if any(_MD_BLOCK_RE.match(l) for l in lines):
        return None
    for delim in _DELIMITERS:
        rows = _try_delimiter(lines, delim)
        if rows:
            return rows
    return None


def is_table(text: str) -> bool:
    return parse_table(text) is not None


def _pad(rows: list[list[str]]) -> tuple[list[list[str]], list[int]]:
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    widths = [max(len(r[i]) for r in rows) for i in range(width)]
    return rows, widths


def rows_to_aligned_text(rows: list[list[str]]) -> str:
    """Monospace columns separated by two spaces; survives Slack code blocks."""
    rows, widths = _pad(rows)
    out = []
    for r in rows:
        cells = [c.ljust(widths[i]) for i, c in enumerate(r)]
        out.append("  ".join(cells).rstrip())
    return "\n".join(out)


def rows_to_md_table(rows: list[list[str]]) -> str:
    rows, widths = _pad(rows)
    widths = [max(w, 3) for w in widths]
    fmt = lambda r: "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(r)) + " |"
    lines = [fmt(rows[0]), "| " + " | ".join("-" * w for w in widths) + " |"]
    lines += [fmt(r) for r in rows[1:]]
    return "\n".join(lines)


def rows_to_html_table(rows: list[list[str]], css: str = "") -> str:
    """HTML table, first row as header. *css* is prepended verbatim if given."""
    rows, _ = _pad(rows)
    parts = [css, "<table>", "<thead><tr>"]
    parts += [f"<th>{html_mod.escape(c)}</th>" for c in rows[0]]
    parts.append("</tr></thead>")
    if len(rows) > 1:
        parts.append("<tbody>")
        for r in rows[1:]:
            parts.append("<tr>" + "".join(f"<td>{html_mod.escape(c)}</td>" for c in r) + "</tr>")
        parts.append("</tbody>")
    parts.append("</table>")
    return "".join(parts)


def md_pipe_table_to_rows(block: str) -> list[list[str]]:
    """Parse a markdown pipe table block into rows, dropping the separator row."""
    rows = []
    for line in block.strip().split("\n"):
        if re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if any(cells):
            rows.append(cells)
    return rows
