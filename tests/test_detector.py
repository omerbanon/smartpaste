"""Content detection tests: one table per content type, plus known edge cases."""

import pytest

from smartpaste.constants import ContentType
from smartpaste.detector import detect

MD, CODE, TABLE, TERM, PLAIN = (
    ContentType.MARKDOWN,
    ContentType.CODE,
    ContentType.TABLE,
    ContentType.TERMINAL,
    ContentType.PLAIN_TEXT,
)

CASES = [
    # --- Markdown (needs 2+ distinct signals) ---
    ("heading + list", "# Title\n\n- one\n- two", MD),
    ("bold + link", "See **this** and [docs](https://x.io).", MD),
    ("ordered list + inline code", "1. Run `make`\n2. Run `make test`", MD),
    ("blockquote + italic", "> quoted *line*\n\nreply", MD),
    ("pipe table + heading", "## Data\n| a | b |\n|---|---|\n| 1 | 2 |", MD),
    ("fenced block + heading", "# Usage\n```\nnpm start\n```", MD),
    ("strikethrough + bold", "~~old~~ **new** price", MD),
    ("box-drawing table", "┌───┬───┐\n│ a │ b │\n├───┼───┤\n│ 1 │ 2 │\n└───┴───┘", MD),
    # --- Code ---
    ("python function", "def add(a, b):\n    return a + b\n\nprint(add(1, 2))", CODE),
    ("js with braces", "const x = () => {\n    return [1, 2];\n};", CODE),
    ("json object", '{"name": "smartpaste", "version": 3}', CODE),
    ("json array", "[1, 2, 3]", CODE),
    ("fenced with language", "```python\nimport os\nprint(os.getcwd())\n```", MD),
    # --- Tables ---
    ("tsv", "Name\tAge\nAlice\t30\nBob\t25", TABLE),
    ("csv", "Name,Age,City\nAlice,30,Paris\nBob,25,Rome", TABLE),
    # --- Terminal ---
    ("padded terminal lines", "$ ls" + " " * 40 + "\nfile.txt" + " " * 40 + "\nother.txt" + " " * 40, TERM),
    ("unpadded shell output", "$ ls\nfile.txt\nother.txt", PLAIN),
    # --- Plain text ---
    ("prose with commas", "Hello, world.\nYes, that is fine.", PLAIN),
    ("single sentence", "Can you send me the report by Friday?", PLAIN),
    ("prose with snake_case names", "Set max_retries and retry_delay_ms in the config file.", PLAIN),
    ("prose with one list item", "Shopping:\n- milk", PLAIN),
    ("snake_case + one list item", "Config:\n- set max_retries and retry_delay", PLAIN),
    ("parenthetical prose", "Call me (or text) after the meeting.", PLAIN),
    ("prose with emphasis only", "This is _really_ important.", PLAIN),
    ("short code-like line", "x = 1", PLAIN),
    ("braces in prose", "The set {a, b} has two items.", PLAIN),
    ("not json despite braces", "{this is not json}", PLAIN),
    ("empty", "", PLAIN),
    ("whitespace only", "   \n\t  \n", PLAIN),
]


@pytest.mark.parametrize("text,expected", [(t, e) for _, t, e in CASES], ids=[n for n, _, _ in CASES])
def test_detect(text, expected):
    assert detect(text) == expected
