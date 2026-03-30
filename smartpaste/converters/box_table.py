"""Convert Unicode box-drawing tables to markdown pipe tables.

Box-drawing characters (┌─┬─┐, │, └─┴─┘) are common in CLI tool output
(Claude Code, psql, etc.). This module detects them and converts to standard
markdown pipe tables that all downstream converters already handle.
"""

import re

_BOX_CHARS = frozenset("┌┐└┘├┤┬┴┼─│╔╗╚╝╠╣╦╩╬═║")

_BOX_TOP_RE = re.compile(r"^[┌╔][─═┬╦]*[┐╗]\s*$")
_BOX_BOTTOM_RE = re.compile(r"^[└╚][─═┴╩]*[┘╝]\s*$")
_BOX_SEPARATOR_RE = re.compile(r"^[├╠][─═┼╬]*[┤╣]\s*$")
_BOX_DATA_RE = re.compile(r"[│║]")


def has_box_drawing(text: str) -> bool:
    """Return True if *text* contains any Unicode box-drawing characters."""
    return bool(_BOX_CHARS & set(text))


def convert_box_tables_to_markdown(text: str) -> str:
    """Replace box-drawing tables in *text* with markdown pipe tables.

    Non-table lines pass through unchanged.  Handles both single-line
    (─│┌┐└┘├┤┬┴┼) and double-line (═║╔╗╚╝╠╣╦╩╬) styles.
    """
    lines = text.split("\n")

    # Strip consistent leading indentation
    non_empty = [l for l in lines if l.strip()]
    if non_empty:
        min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
        if min_indent > 0:
            lines = [l[min_indent:] if len(l) >= min_indent else l for l in lines]

    result: list[str] = []
    header_emitted = False  # tracks whether we've seen a separator after data
    data_rows_since_sep = 0  # counts data rows to know when to auto-insert separator

    for line in lines:
        stripped = line.strip()

        # Top border → skip
        if _BOX_TOP_RE.match(stripped):
            header_emitted = False
            data_rows_since_sep = 0
            continue

        # Bottom border → skip, but auto-insert separator if none was seen
        if _BOX_BOTTOM_RE.match(stripped):
            if not header_emitted and data_rows_since_sep > 0:
                # Peek at last data row to determine column count
                last_data = result[-1] if result else ""
                col_count = last_data.count("|") - 1
                if col_count > 0:
                    sep = "| " + " | ".join("---" for _ in range(col_count)) + " |"
                    # Insert separator after first data row
                    first_data_idx = len(result) - data_rows_since_sep
                    result.insert(first_data_idx + 1, sep)
            header_emitted = False
            data_rows_since_sep = 0
            continue

        # Separator row → markdown separator (only first one after header)
        if _BOX_SEPARATOR_RE.match(stripped):
            if not header_emitted and data_rows_since_sep > 0:
                # Count columns from previous data row
                last_data = result[-1] if result else ""
                col_count = last_data.count("|") - 1
                if col_count > 0:
                    result.append(
                        "| " + " | ".join("---" for _ in range(col_count)) + " |"
                    )
                    header_emitted = True
            # Additional separators (mid-table) → skip
            continue

        # Data row with box-drawing delimiters
        if _BOX_DATA_RE.search(stripped):
            # Split on │ or ║, strip outer empty segments
            cells = re.split(r"[│║]", stripped)
            # Remove leading/trailing empty cells from outer borders
            if cells and not cells[0].strip():
                cells = cells[1:]
            if cells and not cells[-1].strip():
                cells = cells[:-1]
            md_row = "| " + " | ".join(c.strip() for c in cells) + " |"
            result.append(md_row)
            data_rows_since_sep += 1
            continue

        # Non-table line → pass through
        result.append(line)

    return "\n".join(result)
