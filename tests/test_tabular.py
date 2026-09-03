"""Tests for delimiter-separated table parsing (tab, comma, semicolon)."""

from smartpaste.converters.tabular import parse_table, rows_to_aligned_text


TSV = "Name\tAge\tCity\nAlice\t30\tParis\nBob\t25\tRome"
CSV = "Name,Age,City\nAlice,30,Paris\nBob,25,Rome"
CSV_QUOTED = 'Name,Age,City\n"Smith, Alice",30,Paris\nBob,25,"Rome, IT"'
SEMI = "Name;Age;City\nAlice;30;Paris\nBob;25;Rome"
PROSE = "Hello, world.\nYes, that is fine."
MD_LIST = "- one, two\n- three, four"


def test_parses_tab_separated():
    assert parse_table(TSV) == [["Name", "Age", "City"], ["Alice", "30", "Paris"], ["Bob", "25", "Rome"]]


def test_parses_comma_separated():
    assert parse_table(CSV) == [["Name", "Age", "City"], ["Alice", "30", "Paris"], ["Bob", "25", "Rome"]]


def test_comma_inside_quotes_stays_in_one_cell():
    rows = parse_table(CSV_QUOTED)
    assert rows[1] == ["Smith, Alice", "30", "Paris"]
    assert rows[2] == ["Bob", "25", "Rome, IT"]


def test_parses_semicolon_separated():
    assert parse_table(SEMI)[1] == ["Alice", "30", "Paris"]


def test_prose_with_commas_is_not_a_table():
    assert parse_table(PROSE) is None


def test_markdown_list_with_commas_is_not_a_table():
    assert parse_table(MD_LIST) is None


def test_single_line_is_not_a_table():
    assert parse_table("a,b,c") is None


def test_aligned_text_pads_columns_to_equal_width():
    rows = [["Name", "Age"], ["Alice", "30"], ["Bo", "7"]]
    out = rows_to_aligned_text(rows)
    lines = out.split("\n")
    assert lines[0] == "Name   Age"
    assert lines[1] == "Alice  30"
    assert lines[2] == "Bo     7"


def test_sentences_with_one_comma_each_are_not_a_table():
    prose = "I went to Paris, then Rome.\nIt was nice, really.\nSee you, bye."
    assert parse_table(prose) is None
