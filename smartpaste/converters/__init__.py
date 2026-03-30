"""Converter registry for SmartPaste.

Maps (ContentType, TargetFormat) pairs to converter functions.
Each converter takes a plain-text string and returns a dict with
keys 'html' and/or 'plain' to be written to the clipboard.
"""

import logging
from collections.abc import Callable

from smartpaste.constants import ContentType, TargetFormat

log = logging.getLogger(__name__)

ConverterResult = dict[str, str | None]  # {"html": ..., "plain": ...}
ConverterFn = Callable[[str], ConverterResult]

_registry: dict[tuple[ContentType, TargetFormat], ConverterFn] = {}


def register(content_type: ContentType, target_format: TargetFormat):
    """Decorator to register a converter function."""
    def decorator(fn: ConverterFn) -> ConverterFn:
        _registry[(content_type, target_format)] = fn
        log.debug("Registered converter: %s → %s", content_type, target_format)
        return fn
    return decorator


def convert(content_type: ContentType, target_format: TargetFormat, text: str) -> ConverterResult:
    """Look up and run the appropriate converter."""
    from smartpaste.converters.box_table import has_box_drawing, convert_box_tables_to_markdown
    if has_box_drawing(text):
        text = convert_box_tables_to_markdown(text)
    fn = _registry.get((content_type, target_format))
    if fn is None:
        log.warning("No converter for %s → %s, returning plain text", content_type, target_format)
        return {"html": None, "plain": text}
    return fn(text)


# Import converter modules so their @register decorators execute.
import smartpaste.converters.md_to_html  # noqa: E402, F401
import smartpaste.converters.md_to_slack  # noqa: E402, F401
import smartpaste.converters.to_cli  # noqa: E402, F401
import smartpaste.converters.table_to_formats  # noqa: E402, F401
import smartpaste.converters.terminal_clean  # noqa: E402, F401
