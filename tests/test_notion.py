"""Notion target: listed for Markdown and passes the Markdown through untouched."""

from smartpaste.constants import FORMAT_OPTIONS, ContentType, TargetFormat
from smartpaste.converters import convert


def test_notion_offered_for_markdown():
    assert TargetFormat.NOTION in FORMAT_OPTIONS[ContentType.MARKDOWN]


def test_notion_passthrough_keeps_markdown():
    md = "# Title\n\n- **bold** item\n- [link](https://example.com)"
    result = convert(ContentType.MARKDOWN, TargetFormat.NOTION, md)
    assert result == {"html": None, "plain": md}
