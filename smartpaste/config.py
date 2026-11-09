"""Config management for SmartPaste — loads/saves user settings from ~/.smartpaste/config.json.

All defaults live here so the rest of the app can import them.
Config is re-read on each AI call so edits take effect immediately.
"""

import json
import logging
from pathlib import Path

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
    "api_key": "",
    "model": DEFAULT_MODEL,
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "presets": DEFAULT_PRESETS,
}


def load_config() -> dict:
    """Read config JSON, merging with defaults for any missing keys."""
    config = dict(_DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update(saved)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to read config file, using defaults: %s", exc)
    return config


def save_config(config: dict) -> None:
    """Write config dict to JSON, creating ~/.smartpaste/ if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    log.info("Config saved to %s", CONFIG_FILE)


def is_configured() -> bool:
    """Return True if config file exists and has a non-empty API key."""
    if not CONFIG_FILE.exists():
        return False
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("api_key", "").strip())
    except (json.JSONDecodeError, OSError):
        return False
