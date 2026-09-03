"""Markdown → HTML converter for Google Docs, Gmail, and similar rich-text targets."""

import html as htmllib
import re

import markdown as md

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register

_LIST_RE = re.compile(r"^\s*([-*+]|\d+\.)\s+\S")


def _prep_markdown_lists(text: str) -> str:
    """Inject blank lines around list blocks so python-markdown parses them.

    Python-markdown only recognizes `- item` / `1. item` as a list when a blank
    line separates it from preceding paragraph text, and again when the list
    ends. Users paste "lazy" markdown without those blanks — without this prep
    step, lists get flattened into `<br />`-joined paragraphs.

    Indented continuation lines under a list item are preserved as part of the
    list (not split into a new paragraph).
    """
    lines = text.split("\n")
    out: list[str] = []
    in_list = False

    for line in lines:
        blank = not line.strip()
        is_list = bool(_LIST_RE.match(line))
        indented = line.startswith((" ", "\t"))

        if is_list and not in_list:
            if out and out[-1].strip():
                out.append("")
            in_list = True
        elif in_list and not blank and not is_list and not indented:
            if out and out[-1].strip():
                out.append("")
            in_list = False

        out.append(line)

    return "\n".join(out)

# Extensions that cover most common markdown features
_MD_EXTENSIONS = [
    "tables",
    "fenced_code",
    "codehilite",
    "nl2br",
    "sane_lists",
    "smarty",
    "pymdownx.tilde",  # ~~strikethrough~~ → <del>
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
    text = _prep_markdown_lists(text)
    html_body = md.markdown(
        text,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
    )
    return f"{_WRAPPER_CSS}\n{html_body}"


def _plain_to_html(text: str) -> str:
    """Wrap plain text in paragraph HTML so rich-text apps preserve structure.

    Blank-line separated blocks become <p>; internal newlines become <br />.
    """
    blocks = re.split(r"\n\s*\n", text.strip())
    parts = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        escaped = htmllib.escape(block).replace("\n", "<br />\n")
        parts.append(f"<p>{escaped}</p>")
    return f"{_WRAPPER_CSS}\n" + "\n".join(parts)


def _strip_html_tags(html: str) -> str:
    """Crude tag stripper for the plain-text fallback."""
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


@register(ContentType.PLAIN_TEXT, TargetFormat.GOOGLE_DOCS)
def plain_to_google_docs(text: str) -> dict[str, str | None]:
    return {"html": _plain_to_html(text), "plain": text}


@register(ContentType.PLAIN_TEXT, TargetFormat.GMAIL)
def plain_to_gmail(text: str) -> dict[str, str | None]:
    return {"html": _plain_to_html(text), "plain": text}


@register(ContentType.PLAIN_TEXT, TargetFormat.PLAIN)
def plain_to_plain(text: str) -> dict[str, str | None]:
    return {"html": None, "plain": text}
