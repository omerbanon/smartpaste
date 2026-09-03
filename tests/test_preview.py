"""Preview panel rendering tests (HTML only, no window)."""

from smartpaste.preview import _render_to_html

CSV = "Name,Age,City\nAlice,30,Paris\nBob,25,Rome"
CSV_QUOTED = 'Name,Age\n"Smith, Alice",30'


def test_csv_preview_renders_as_html_table():
    html = _render_to_html(CSV)
    assert "<table>" in html
    assert "<th>Name</th>" in html
    assert "<td>Paris</td>" in html
    assert "2 rows" in html


def test_csv_preview_keeps_quoted_comma_in_one_cell():
    html = _render_to_html(CSV_QUOTED)
    assert "<td>Smith, Alice</td>" in html
