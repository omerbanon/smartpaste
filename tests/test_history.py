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


# --- watcher -----------------------------------------------------------------

from smartpaste.history import ClipboardWatcher, CONCEALED_TYPES


class FakeBoard:
    def __init__(self):
        self.count = 0
        self.own = -1
        self.types = ["public.utf8-plain-text"]
        self.text = "hello"

    def watcher(self, history):
        return ClipboardWatcher(
            history,
            change_count=lambda: self.count,
            own_change_count=lambda: self.own,
            read_types=lambda: self.types,
            read_text=lambda: self.text,
        )


def test_watcher_records_new_text():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1
    assert w.poll() is True
    assert h.items()[0].text == "hello"


def test_watcher_ignores_unchanged_counter():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; w.poll()
    b.text = "changed but counter did not"
    assert w.poll() is False
    assert len(h) == 1


def test_watcher_skips_smartpaste_own_writes():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; b.own = 1
    assert w.poll() is False
    assert len(h) == 0


def test_watcher_skips_concealed_pasteboards():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; b.types = ["public.utf8-plain-text", CONCEALED_TYPES[0]]
    assert w.poll() is False


def test_watcher_skips_non_text():
    b, h = FakeBoard(), ClipboardHistory()
    w = b.watcher(h)
    b.count = 1; b.text = None; b.types = ["public.png"]
    assert w.poll() is False
