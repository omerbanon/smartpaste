"""Rich text (HTML from the clipboard) → Markdown.

Used for the "Markdown" target, which appears when the clipboard holds HTML:
copy from Google Docs, Confluence, Gmail or a web page, paste clean Markdown
into GitHub, an editor or an LLM chat.
"""

import re

from bs4 import BeautifulSoup
from markdownify import markdownify

# Tags that mean the HTML carries real structure worth converting.
_RICH_TAGS = re.compile(r"<(p|h[1-6]|li|ul|ol|strong|b|em|i|a|table|pre|code|blockquote|br)\b", re.I)
_BOLD_STYLE = re.compile(r"font-weight\s*:\s*(bold|[6-9]00)", re.I)
_ITALIC_STYLE = re.compile(r"font-style\s*:\s*italic", re.I)
_NORMAL_WEIGHT = re.compile(r"font-weight\s*:\s*(normal|[1-4]00)", re.I)


def has_rich_html(html: str | None) -> bool:
    return bool(html and _RICH_TAGS.search(html))


def _clean(html: str) -> str:
    """Normalize editor quirks markdownify can't see (it ignores CSS)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "meta", "title", "head"]):
        tag.decompose()
    # Google Docs wraps the whole selection in <b style="font-weight:normal">
    for tag in soup.find_all("b"):
        if _NORMAL_WEIGHT.search(tag.get("style", "")):
            tag.unwrap()
    # Google Docs marks bold/italic with inline styles on <span>
    for span in soup.find_all("span"):
        style = span.get("style", "")
        if _BOLD_STYLE.search(style):
            span.wrap(soup.new_tag("strong"))
        if _ITALIC_STYLE.search(style):
            span.wrap(soup.new_tag("em"))
    return str(soup)


def html_to_markdown(html: str) -> str:
    md = markdownify(_clean(html), heading_style="ATX", bullets="-", strong_em_symbol="*")
    md = re.sub(r"[ \t]+\n", "\n", md)  # trailing spaces
    md = re.sub(r"\n{3,}", "\n\n", md)  # runs of blank lines
    return md.strip() + "\n"
