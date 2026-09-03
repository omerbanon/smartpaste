"""Content detection tests."""

from smartpaste.constants import ContentType
from smartpaste.detector import detect


def test_tsv_is_table():
    assert detect("Name\tAge\nAlice\t30\nBob\t25") == ContentType.TABLE


def test_csv_is_table():
    assert detect("Name,Age,City\nAlice,30,Paris\nBob,25,Rome") == ContentType.TABLE


def test_prose_with_commas_is_plain_text():
    assert detect("Hello, world.\nYes, that is fine.") == ContentType.PLAIN_TEXT
