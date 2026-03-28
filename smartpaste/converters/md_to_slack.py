"""Markdown → Slack HTML converter.

Slack's WYSIWYG composer reads HTML from the clipboard (public.html) and
converts it to rich text: <strong> → bold, <em> → italic, <ul>/<ol> → lists,
<pre><code> → code blocks, <blockquote> → quotes, <a> → links.

Slack does NOT support: tables, headings (converted to bold), or <style> blocks.
We generate clean, minimal HTML optimized for Slack's parser.
"""

import re

import markdown as md

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register

# Extensions — no codehilite (Slack ignores inline styles), no smarty
_MD_EXTENSIONS = [
    "fenced_code",
    "sane_lists",
    "nl2br",
    "pymdownx.tilde",  # ~~strikethrough~~ → <del>
]


def _md_to_slack_html(text: str) -> str:
    """Convert markdown to clean HTML that Slack's composer understands."""
    # Pre-process: convert markdown tables to plain text (Slack has no table support)
    text = _tables_to_text(text)

    html = md.markdown(text, extensions=_MD_EXTENSIONS)

    # Post-process: convert headings to bold paragraphs (Slack has no headings)
    html = re.sub(r"<h[1-6]>(.*?)</h[1-6]>", r"<p><strong>\1</strong></p>", html)

    # Remove any horizontal rules (Slack ignores them)
    html = re.sub(r"<hr\s*/?>", "", html)

    return html


def _tables_to_text(text: str) -> str:
    """Convert markdown tables to plain-text representation before HTML conversion."""
    def _convert_table(m: re.Match) -> str:
        block = m.group(0).strip()
        lines = block.split("\n")
        rows = []
        for line in lines:
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        # Format as "key: value" for 2-col, comma-join for 3+
        headers = rows[0]
        data = rows[1:]
        if not data:
            return ", ".join(headers)
        result = []
        for row in data:
            result.append(", ".join(row))
        return "\n".join(result)

    return re.sub(
        r"(?:^\|.+\|[ \t]*\n)+",
        _convert_table,
        text,
        flags=re.MULTILINE,
    )


def _strip_tags(html: str) -> str:
    """Strip HTML tags for plain-text fallback."""
    clean = re.sub(r"<[^>]+>", "", html)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


@register(ContentType.MARKDOWN, TargetFormat.SLACK)
def md_to_slack(text: str) -> dict[str, str | None]:
    """Convert markdown to HTML for Slack's WYSIWYG composer.

    Slack reads public.html from the clipboard and converts:
    <strong> → bold, <em> → italic, <ul>/<ol> → lists,
    <pre><code> → code blocks, <a> → links, <blockquote> → quotes.
    """
    html = _md_to_slack_html(text)
    return {"html": html, "plain": _strip_tags(html)}
