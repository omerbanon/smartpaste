"""Slack converter tests: tables and terminal text must paste as code blocks."""

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import convert

CSV = "Name,Age,City\nAlice,30,Paris\nBob,25,Rome"
MD_TABLE = "Results:\n\n| Name | Age |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |\n\nDone."
TERMINAL = (
    "PID   COMMAND          %CPU" + " " * 20 + "\n"
    "123   node             12.0" + " " * 20 + "\n"
    "456   *python*         3.5" + " " * 21 + "\n"
)


def test_csv_table_to_slack_is_a_code_block_with_aligned_columns():
    out = convert(ContentType.TABLE, TargetFormat.SLACK, CSV)
    assert "<table" not in out["html"]
    assert "<pre>" in out["html"]
    assert "Alice  30   Paris" in out["html"]
    assert out["plain"].startswith("```")


def test_markdown_table_to_slack_is_a_code_block_and_keeps_header():
    out = convert(ContentType.MARKDOWN, TargetFormat.SLACK, MD_TABLE)
    assert "<pre>" in out["html"]
    assert "Name" in out["html"] and "Alice  30" in out["html"]
    assert "Results:" in out["html"] and "Done." in out["html"]


def test_terminal_to_slack_is_one_code_block_without_markdown_parsing():
    out = convert(ContentType.TERMINAL, TargetFormat.SLACK, TERMINAL)
    assert out["html"].count("<pre>") == 1
    assert "<em>" not in out["html"] and "<strong>" not in out["html"]
    assert "*python*" in out["html"]
    assert "123   node             12.0" in out["html"]
