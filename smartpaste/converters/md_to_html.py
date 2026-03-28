"""Markdown → HTML converter for Google Docs, Gmail, and similar rich-text targets."""

import markdown as md

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register

# Extensions that cover most common markdown features
_MD_EXTENSIONS = [
    "tables",
    "fenced_code",
    "codehilite",
    "nl2br",
    "sane_lists",
    "smarty",
]

_MD_EXTENSION_CONFIGS = {
    "codehilite": {
        "css_class": "highlight",
        "guess_lang": True,
        "noclasses": True,  # inline styles so pasting into Docs/Gmail works
    },
}

# Minimal inline styles so rich-text apps render things reasonably
_WRAPPER_CSS = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px; color: #1a1a1a; }
  code { background: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-size: 13px; }
  pre { background: #f5f5f5; padding: 12px; border-radius: 6px; overflow-x: auto; }
  blockquote { border-left: 3px solid #ccc; padding-left: 12px; color: #555; margin: 8px 0; }
  table { border-collapse: collapse; margin: 8px 0; }
  th, td { border: 1px solid #ddd; padding: 6px 12px; }
  th { background: #f5f5f5; }
  h1, h2, h3, h4, h5, h6 { margin-top: 16px; margin-bottom: 8px; }
  ul, ol { padding-left: 24px; }
  a { color: #1a73e8; }
</style>
""".strip()


def _md_to_html(text: str) -> str:
    """Convert markdown text to a full HTML snippet with inline-friendly styles."""
    html_body = md.markdown(
        text,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
    )
    return f"{_WRAPPER_CSS}\n{html_body}"


def _strip_html_tags(html: str) -> str:
    """Crude tag stripper for the plain-text fallback."""
    import re
    clean = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


@register(ContentType.MARKDOWN, TargetFormat.GOOGLE_DOCS)
def md_to_google_docs(text: str) -> dict[str, str | None]:
    html = _md_to_html(text)
    return {"html": html, "plain": _strip_html_tags(html)}


@register(ContentType.MARKDOWN, TargetFormat.GMAIL)
def md_to_gmail(text: str) -> dict[str, str | None]:
    html = _md_to_html(text)
    return {"html": html, "plain": _strip_html_tags(html)}


@register(ContentType.MARKDOWN, TargetFormat.PLAIN)
def md_to_plain(text: str) -> dict[str, str | None]:
    """Strip markdown formatting, return plain text only."""
    html = _md_to_html(text)
    return {"html": None, "plain": _strip_html_tags(html)}
