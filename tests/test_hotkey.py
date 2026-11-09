"""Hotkey string parsing (no registration)."""

import pytest

from smartpaste.hotkey import DEFAULT_HOTKEY, PRESET_HOTKEYS, format_hotkey, normalize_hotkey, parse_hotkey


def test_default_parses():
    vk, mask = parse_hotkey(DEFAULT_HOTKEY)
    assert vk == 9  # kVK_ANSI_V
    assert format_hotkey(DEFAULT_HOTKEY) == "⇧⌘V"


@pytest.mark.parametrize("spec", PRESET_HOTKEYS)
def test_presets_are_valid(spec):
    assert normalize_hotkey(spec) == spec


@pytest.mark.parametrize(
    "spec,expected",
    [("Shift+Cmd+V", "cmd+shift+v"), ("alt+ctrl+space", "ctrl+option+space"), ("cmd+f5", "cmd+f5")],
)
def test_normalize(spec, expected):
    assert normalize_hotkey(spec) == expected


@pytest.mark.parametrize("spec", ["", "v", "shift+v", "cmd+", "cmd+shift+enter", "hyper+v"])
def test_invalid(spec):
    with pytest.raises(ValueError):
        parse_hotkey(spec)


def test_recorder_maps_events():
    from smartpaste.hotkey_recorder import spec_from_event

    cmd, shift, option = 1 << 20, 1 << 17, 1 << 19
    assert spec_from_event(9, cmd | shift) == "cmd+shift+v"
    assert spec_from_event(49, cmd | option) == "cmd+option+space"
    assert spec_from_event(9, shift) is None  # needs Cmd, Ctrl or Option
    assert spec_from_event(36, cmd) is None  # Return isn't supported
