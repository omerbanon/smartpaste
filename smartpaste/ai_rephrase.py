"""AI rephrase integration for SmartPaste — calls Claude API to reformat text.

Usage:
    from smartpaste.ai_rephrase import rephrase, get_api_key

    key = get_api_key()
    if key:
        result = rephrase("Make more concise", clipboard_text)
"""

import logging

import anthropic

from smartpaste.config import load_config

log = logging.getLogger(__name__)

_TIMEOUT = 30.0


def get_api_key() -> str | None:
    """Return the Anthropic API key from config, or None if missing."""
    config = load_config()
    key = config.get("api_key", "").strip()
    if not key:
        log.warning("API key not found in config")
        return None
    return key


def rephrase(prompt: str, text: str) -> str:
    """Call Claude to rephrase/reformat text according to the given prompt.

    Args:
        prompt: The user's instruction (e.g. "Make more concise").
        text: The clipboard text to reformat.

    Returns:
        The reformatted text from Claude.

    Raises:
        anthropic.APIError: On API failures.
        anthropic.APITimeoutError: If the request exceeds the timeout.
        ValueError: If no API key is configured.
    """
    config = load_config()
    key = config.get("api_key", "").strip()
    if not key:
        raise ValueError("API key not configured — open Settings to add one")

    model = config.get("model", "claude-haiku-4-5-20251001")
    system_prompt = config.get("system_prompt", "")

    client = anthropic.Anthropic(api_key=key, timeout=_TIMEOUT)

    user_message = f"Instruction: {prompt}\n\nText:\n{text}"

    log.info("AI rephrase: sending request (model=%s, prompt=%r)", model, prompt)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    result = response.content[0].text
    log.info("AI rephrase: received %d chars", len(result))
    return result
