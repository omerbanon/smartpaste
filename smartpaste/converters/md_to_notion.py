"""Markdown → Notion converter.

Notion natively parses standard Markdown on paste, so this is a passthrough.
We keep the converter registered so the popup can offer "Notion" as a target
and the pipeline stays consistent.
"""

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register


@register(ContentType.MARKDOWN, TargetFormat.NOTION)
def md_to_notion(text: str) -> dict[str, str | None]:
    """Passthrough — Notion handles standard Markdown natively."""
    return {"html": None, "plain": text}
