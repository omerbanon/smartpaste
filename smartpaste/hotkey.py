"""Global hotkey registration via quickmachotkey.

The shortcut is a config string such as "cmd+shift+v" or "ctrl+option+space":
modifiers (cmd, shift, option/alt, ctrl/control) joined with "+", then one key
(a-z, 0-9, f1-f20, space). Default: Cmd+Shift+V.
"""

import logging
from collections.abc import Callable

from quickmachotkey import quickHotKey
from quickmachotkey import constants as k

log = logging.getLogger(__name__)

DEFAULT_HOTKEY = "cmd+shift+v"

# Offered in the menu bar "Hotkey" submenu. Cmd+Shift+V is "Paste and Match
# Style" in many apps, so the others are there for people who need it back.
PRESET_HOTKEYS: list[str] = [
    "cmd+shift+v",
    "cmd+option+v",
    "ctrl+option+v",
    "cmd+option+shift+v",
]

_MODIFIERS: dict[str, int] = {
    "cmd": k.cmdKey,
    "command": k.cmdKey,
    "shift": k.shiftKey,
    "option": k.optionKey,
    "alt": k.optionKey,
    "opt": k.optionKey,
    "ctrl": k.controlKey,
    "control": k.controlKey,
}
# Display order and symbols follow the macOS menu convention: ⌃ ⌥ ⇧ ⌘
_SYMBOLS: list[tuple[int, str]] = [(k.controlKey, "⌃"), (k.optionKey, "⌥"), (k.shiftKey, "⇧"), (k.cmdKey, "⌘")]

_KEYS: dict[str, int] = {"space": k.kVK_Space}
_KEYS.update({c: getattr(k, f"kVK_ANSI_{c.upper()}") for c in "abcdefghijklmnopqrstuvwxyz0123456789"})
_KEYS.update({f"f{n}": getattr(k, f"kVK_F{n}") for n in range(1, 21)})
KEYCODE_TO_NAME: dict[int, str] = {code: name for name, code in _KEYS.items()}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Return (virtual_key, modifier_mask) for *spec*. Raises ValueError if invalid."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    *mods, key = parts
    if key not in _KEYS:
        raise ValueError(f"unknown key {key!r}")
    mask = 0
    for mod in mods:
        if mod not in _MODIFIERS:
            raise ValueError(f"unknown modifier {mod!r}")
        mask |= _MODIFIERS[mod]
    if not mask & (k.cmdKey | k.controlKey | k.optionKey):
        raise ValueError("hotkey needs Cmd, Ctrl or Option")
    return _KEYS[key], mask


def normalize_hotkey(spec: str) -> str:
    """Canonical lower-case form, e.g. "Shift+Cmd+V" -> "cmd+shift+v"."""
    vk, mask = parse_hotkey(spec)
    names = {k.cmdKey: "cmd", k.shiftKey: "shift", k.optionKey: "option", k.controlKey: "ctrl"}
    order = [k.cmdKey, k.controlKey, k.optionKey, k.shiftKey]
    return "+".join([names[m] for m in order if mask & m] + [KEYCODE_TO_NAME[vk]])


def format_hotkey(spec: str) -> str:
    """Human label, e.g. "cmd+shift+v" -> "⇧⌘V"."""
    vk, mask = parse_hotkey(spec)
    name = KEYCODE_TO_NAME[vk]
    key = "Space" if name == "space" else name.upper()
    return "".join(sym for m, sym in _SYMBOLS if mask & m) + key


class HotkeyManager:
    """Owns the single global hotkey and swaps it when the setting changes."""

    def __init__(self, callback: Callable[[], None]):
        self._callback = callback
        self._registered = None
        self.spec = DEFAULT_HOTKEY

    def register(self, spec: str | None) -> str:
        """Register *spec* (falling back to the default if invalid). Returns the spec in use."""
        try:
            spec = normalize_hotkey(spec or DEFAULT_HOTKEY)
        except ValueError as exc:
            log.warning("Invalid hotkey %r (%s), using %s", spec, exc, DEFAULT_HOTKEY)
            spec = DEFAULT_HOTKEY
        vk, mask = parse_hotkey(spec)

        if self._registered is not None:
            self._registered.unregister()

        def _on_hotkey() -> None:
            log.debug("Hotkey %s triggered", spec)
            self._callback()

        self._registered = quickHotKey(virtualKey=vk, modifierMask=mask)(_on_hotkey)
        self.spec = spec
        log.info("Global hotkey %s registered", format_hotkey(spec))
        return spec

    def suspend(self) -> None:
        """Release the hotkey (while recording a new one, so the old combo reaches the recorder)."""
        if self._registered is not None:
            self._registered.unregister()

    def resume(self) -> None:
        if self._registered is not None:
            self._registered.register()
