"""Config management for SmartPaste — loads/saves user settings from ~/.smartpaste/config.json.

All defaults live here so the rest of the app can import them.
Config is re-read on each AI call so edits take effect immediately.

The API key is not stored in config.json. It lives in the macOS Keychain
(keychain.py): load_config() never returns it, get_api_key() reads it, and
save_config() moves an "api_key" entry into the Keychain.
"""

import json
import logging
from pathlib import Path

from smartpaste import keychain

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".smartpaste"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_SYSTEM_PROMPT = (
    "You are a text reformatting assistant for a clipboard tool.\n"
    "The user will give you an instruction and some text.\n"
    "Apply the instruction to the text and return ONLY the result.\n"
    "Do not include any explanation, preamble, commentary, or wrapping.\n"
    "Do not add markdown code fences unless the user explicitly asks for code.\n"
    "Preserve the original language unless told to translate."
)

DEFAULT_PRESETS: list[str] = [
    "Fix grammar and spelling",
    "Make more concise",
    "Summarize in 2-3 sentences",
    "Convert to bullet points",
    "Make more formal / professional",
    "Format as a Slack message",
]

DEFAULT_MODEL = "claude-haiku-5-5"

# Shown when the Models API can't be reached. Settings also merges in the live
# list from client.models.list(), so this only needs to be a sensible fallback.
AVAILABLE_MODELS: dict[str, str] = {
    "claude-haiku-5-5": "Haiku 5.5 (fast, cheap)",
    "claude-sonnet-5-5": "Sonnet 5.5 (balanced)",
    "claude-opus-5-5": "Opus 5.5 (most capable, slower)",
}


def model_choices(current: str | None, fetched: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(model_id, label) pairs for the Settings model picker.

    Known models first, then any extra ones from the Models API, then the saved
    model if it's in neither list, so an older choice keeps working instead of
    being silently reset.
    """
    choices = dict(AVAILABLE_MODELS)
    for model_id, name in (fetched or {}).items():
        choices.setdefault(model_id, name)
    if current and current not in choices:
        choices[current] = f"{current} (saved)"
    return list(choices.items())


def fetch_models(api_key: str, timeout: float = 10.0) -> dict[str, str]:
    """Return {model_id: display_name} from the Anthropic Models API ({} on any failure)."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        return {m.id: m.display_name for m in client.models.list(limit=100)}
    except Exception as exc:  # network, auth, old SDK: fall back to the static list
        log.warning("Could not list models: %s", exc)
        return {}

_DEFAULTS: dict = {
    "model": DEFAULT_MODEL,
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "presets": DEFAULT_PRESETS,
}


def _read_file() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read config file, using defaults: %s", exc)
        return {}


def _write_file(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config() -> dict:
    """Read config JSON, merged with defaults for any missing keys. Never includes the API key."""
    config = dict(_DEFAULTS)
    config.update(_read_file())
    config.pop("api_key", None)
    return config


def save_config(config: dict) -> None:
    """Write config to JSON, creating ~/.smartpaste/ if needed.

    An "api_key" entry is stored in the Keychain (or removed from it when
    empty) and kept out of the file. If the Keychain refuses the write, the
    key stays in the file so the app keeps working, and a warning is logged.
    """
    data = dict(config)
    if "api_key" in data:
        key = str(data.pop("api_key") or "").strip()
        if not key:
            keychain.delete_secret()
        elif not keychain.set_secret(key):
            log.warning("Keychain unavailable; keeping the API key in %s", CONFIG_FILE)
            data["api_key"] = key
    _write_file(data)
    log.info("Config saved to %s", CONFIG_FILE)


def get_api_key() -> str:
    """The Anthropic API key from the Keychain (or a not-yet-migrated config.json), or ""."""
    key = keychain.get_secret()
    if key:
        return key.strip()
    return str(_read_file().get("api_key") or "").strip()


def migrate_api_key_to_keychain() -> None:
    """Move a plain-text api_key from config.json into the Keychain (run once at startup)."""
    data = _read_file()
    key = str(data.get("api_key") or "").strip()
    if "api_key" not in data:
        return
    if key and not keychain.set_secret(key):
        log.warning("Could not move the API key to the Keychain; leaving it in config.json")
        return
    data.pop("api_key")
    _write_file(data)
    log.info("Moved the API key from config.json to the Keychain")


def is_configured() -> bool:
    """Return True if an API key is available."""
    return bool(get_api_key())
