"""AI rephrase integration for SmartPaste — calls Claude API to reformat text.

Usage:
    from smartpaste.ai_rephrase import rephrase, get_api_key

    key = get_api_key()
    if key:
        result = rephrase("Make more concise", clipboard_text, on_text=print_progress)
        if result.truncated:
            ...
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from smartpaste.config import DEFAULT_MODEL, load_config

log = logging.getLogger(__name__)

# Per-read timeout. With streaming this bounds the gap between chunks, not the
# whole response, so long rephrases don't time out.
_TIMEOUT = 30.0
# High enough for long documents; every model in AVAILABLE_MODELS (and the
# older 4.5 models) accepts it. Streaming keeps it clear of HTTP timeouts.
MAX_TOKENS = 32000
# How often partial text is handed to on_text (seconds).
_PARTIAL_INTERVAL = 0.08

# Model families that take output_config.effort. Rephrasing is simple work, so
# "low" keeps it fast. Older models (Haiku/Sonnet 4.5) reject the parameter.
_EFFORT_FAMILIES = ("claude-haiku-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5")


@dataclass
class RephraseResult:
    text: str
    truncated: bool  # True when Claude hit MAX_TOKENS and the text is cut off


def get_api_key() -> str | None:
    """Return the Anthropic API key, or None if missing."""
    from smartpaste.config import get_api_key as _get

    key = _get()
    if not key:
        log.warning("API key not configured")
        return None
    return key


def _request_kwargs(model: str, system_prompt: str, user_message: str) -> dict:
    kwargs: dict = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    if model.startswith(_EFFORT_FAMILIES):
        kwargs["output_config"] = {"effort": "low"}
    return kwargs


def collect_result(message) -> RephraseResult:
    """Join every text block of a final Message and flag truncation."""
    if message.stop_reason == "refusal":
        raise RuntimeError("Claude declined to rephrase this text")
    text = "".join(block.text for block in message.content if block.type == "text")
    return RephraseResult(text=text, truncated=message.stop_reason == "max_tokens")


def rephrase(
    prompt: str,
    text: str,
    on_text: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> RephraseResult | None:
    """Stream Claude's rewrite of *text* according to *prompt*.

    Args:
        prompt: The user's instruction (e.g. "Make more concise").
        text: The clipboard text to reformat.
        on_text: Called (on this worker thread) with the text received so far,
            at most every ~80 ms while the response streams in.
        should_stop: Polled between chunks; returning True abandons the request.

    Returns:
        The full result, or None if should_stop() cancelled it.

    Raises:
        anthropic.APIError: On API failures (including timeouts).
        RuntimeError: If Claude refuses the request.
        ValueError: If no API key is configured.
    """
    key = get_api_key()
    if not key:
        raise ValueError("API key not configured — open Settings to add one")

    config = load_config()
    model = config.get("model") or DEFAULT_MODEL
    system_prompt = config.get("system_prompt", "")
    client = anthropic.Anthropic(api_key=key, timeout=_TIMEOUT)
    user_message = f"Instruction: {prompt}\n\nText:\n{text}"

    log.info("AI rephrase: sending request (model=%s, %d chars of text)", model, len(text))
    received: list[str] = []
    last_push = 0.0
    with client.messages.stream(**_request_kwargs(model, system_prompt, user_message)) as stream:
        for chunk in stream.text_stream:
            if should_stop and should_stop():
                log.info("AI rephrase: cancelled")
                return None
            received.append(chunk)
            now = time.monotonic()
            if on_text and now - last_push >= _PARTIAL_INTERVAL:
                on_text("".join(received))
                last_push = now
        result = collect_result(stream.get_final_message())

    if result.truncated:
        log.warning("AI rephrase: output hit max_tokens (%d) and is cut off", MAX_TOKENS)
    log.info("AI rephrase: received %d chars", len(result.text))
    return result
