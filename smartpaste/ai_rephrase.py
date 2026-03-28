"""AI rephrase integration for SmartPaste — calls Claude API to reformat text.

Usage:
    from smartpaste.ai_rephrase import rephrase, get_api_key

    key = get_api_key()
    if key:
        result = rephrase("Make more concise", clipboard_text)
"""

import logging
from pathlib import Path

from dotenv import load_dotenv
import os

import anthropic

log = logging.getLogger(__name__)

# Load .env from project root (next to smartpaste/ package)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

_SYSTEM_PROMPT = (
    "You are a text reformatting assistant for a clipboard tool.\n"
    "The user will give you an instruction and some text.\n"
    "Apply the instruction to the text and return ONLY the result.\n"
    "Do not include any explanation, preamble, commentary, or wrapping.\n"
    "Do not add markdown code fences unless the user explicitly asks for code.\n"
    "Preserve the original language unless told to translate."
)

_MODEL = "claude-haiku-4-5-20251001"
_TIMEOUT = 30.0


def get_api_key() -> str | None:
    """Return the Anthropic API key from environment, or None if missing."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.warning("ANTHROPIC_API_KEY not found in environment")
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
    key = get_api_key()
    if not key:
        raise ValueError("API key not found — add ANTHROPIC_API_KEY to .env")

    client = anthropic.Anthropic(api_key=key, timeout=_TIMEOUT)

    user_message = f"Instruction: {prompt}\n\nText:\n{text}"

    log.info("AI rephrase: sending request (model=%s, prompt=%r)", _MODEL, prompt)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    result = response.content[0].text
    log.info("AI rephrase: received %d chars", len(result))
    return result
