"""Clipboard HTML → Markdown."""

from smartpaste.converters.html_to_md import has_rich_html, html_to_markdown


def test_basic_structure():
    html = "<h2>Plan</h2><p>Ship <strong>today</strong>, see <a href='https://x.io'>docs</a>.</p><ul><li>one</li><li>two</li></ul>"
    md = html_to_markdown(html)
    assert "## Plan" in md
    assert "**today**" in md
    assert "[docs](https://x.io)" in md
    assert "- one\n- two" in md


def test_google_docs_wrapper_is_not_bold_and_styled_spans_are():
    html = (
        '<meta charset="utf-8"><b style="font-weight:normal;" id="docs-internal-guid-1">'
        '<p><span style="font-weight:400;">plain </span><span style="font-weight:700;">bold</span>'
        '<span style="font-style:italic;"> it</span></p></b>'
    )
    md = html_to_markdown(html)
    assert md.startswith("plain **bold**")
    assert "*it*" in md
    assert not md.startswith("**plain")


def test_rich_html_detection():
    assert has_rich_html("<p>hi</p>")
    assert not has_rich_html(None)
    assert not has_rich_html('<span style="color:red">just text</span>')


def test_markdown_target_only_with_rich_text():
    from smartpaste.constants import ContentType, TargetFormat, format_options

    plain = format_options(ContentType.PLAIN_TEXT)
    rich = format_options(ContentType.PLAIN_TEXT, has_rich_html=True)
    assert TargetFormat.MARKDOWN not in plain
    assert rich[-2:] == [TargetFormat.MARKDOWN, TargetFormat.AI_REPHRASE]
