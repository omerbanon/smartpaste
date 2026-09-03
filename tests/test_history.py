"""Ring buffer rules for clipboard history."""

from smartpaste.history import ClipboardHistory, age_label


def test_newest_first():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2)
    assert [i.text for i in h.items()] == ["b", "a"]


def test_capacity_drops_oldest():
    h = ClipboardHistory(capacity=3)
    for n in range(5):
        h.push(str(n), now=n)
    assert [i.text for i in h.items()] == ["4", "3", "2"]


def test_duplicate_moves_to_top_without_growing():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2); h.push("a", now=3)
    assert [i.text for i in h.items()] == ["a", "b"]
    assert h.items()[0].copied_at == 3


def test_whitespace_only_is_skipped():
    h = ClipboardHistory()
    assert h.push("   \n\t", now=1) is False
    assert len(h) == 0


def test_remove_by_index():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2); h.push("c", now=3)
    h.remove(1)
    assert [i.text for i in h.items()] == ["c", "a"]


def test_touch_moves_item_to_top():
    h = ClipboardHistory()
    h.push("a", now=1); h.push("b", now=2); h.push("c", now=3)
    h.touch(2)
    assert [i.text for i in h.items()] == ["a", "c", "b"]


def test_age_label():
    assert age_label(100, now=130) == "now"
    assert age_label(100, now=100 + 5 * 60) == "5m"
    assert age_label(100, now=100 + 3 * 3600) == "3h"
