"""Markdown → Slack mrkdwn converter.

Slack uses its own 'mrkdwn' syntax which differs from standard Markdown:
- Bold: *text* (not **text**)
- Italic: _text_ (same)
- Strikethrough: ~text~ (not ~~text~~)
- Code: `text` (same) and ```text``` (same)
- Links: <url|text> (not [text](url))
- Headings → bold text (Slack has no heading syntax in messages)
- Blockquote: > text (same)
- Lists: Slack renders plain-text bullets/numbers

The converter stashes code blocks/inline code first to protect them,
then uses placeholders for bold so it doesn't collide with italic conversion.
"""

import re

from smartpaste.constants import ContentType, TargetFormat
from smartpaste.converters import register

# Null-byte delimited placeholders (won't appear in normal text)
_CB = "\x00CB"    # code block
_IC = "\x00IC"    # inline code
_SB = "\x00SB"    # slack bold start
_SE = "\x00SE"    # slack bold end
_BI_S = "\x00BS"  # bold-italic start
_BI_E = "\x00BE"  # bold-italic end


def _convert_md_to_mrkdwn(text: str) -> str:
    """Transform standard Markdown into Slack mrkdwn."""
    result = text

    # --- Phase 1: Stash code (protect from formatting changes) ---
    code_blocks: list[str] = []
    inline_codes: list[str] = []

    def _stash_block(m: re.Match) -> str:
        code_blocks.append(m.group(0))
        return f"{_CB}{len(code_blocks) - 1}\x00"

    def _stash_inline(m: re.Match) -> str:
        inline_codes.append(m.group(0))
        return f"{_IC}{len(inline_codes) - 1}\x00"

    result = re.sub(r"```[\s\S]*?```", _stash_block, result)
    result = re.sub(r"`[^`\n]+`", _stash_inline, result)

    # --- Phase 2: Images (before links — ![alt](url) starts with !) ---
    result = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"<\2|\1>", result)

    # --- Phase 3: Links [text](url) → <url|text> ---
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", result)

    # --- Phase 4: Bold+Italic ***text*** → placeholder (restore as *_text_* later) ---
    result = re.sub(r"\*\*\*([^*]+?)\*\*\*", rf"{_BI_S}\1{_BI_E}", result)

    # --- Phase 5: Bold **text** / __text__ → placeholder (restore as *text* later) ---
    result = re.sub(r"\*\*([^*\n]+?)\*\*", rf"{_SB}\1{_SE}", result)
    result = re.sub(r"__([^_\n]+?)__", rf"{_SB}\1{_SE}", result)

    # --- Phase 6: Italic *text* → _text_ (Slack italic) ---
    # Now safe because all bold ** are already replaced with placeholders
    result = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"_\1_", result)

    # --- Phase 7: Restore bold placeholders → *text* (Slack bold) ---
    result = result.replace(_SB, "*").replace(_SE, "*")
    result = result.replace(_BI_S, "*_").replace(_BI_E, "_*")

    # --- Phase 8: Strikethrough ~~text~~ → ~text~ ---
    result = re.sub(r"~~([^~\n]+?)~~", r"~\1~", result)

    # --- Phase 9: Headings → bold text ---
    result = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", result, flags=re.MULTILINE)

    # --- Phase 10: Horizontal rules ---
    result = re.sub(r"^[-*_]{3,}\s*$", "---", result, flags=re.MULTILINE)

    # --- Phase 11: Tables → code block (Slack has no table support) ---
    def _table_to_code(m: re.Match) -> str:
        table_text = m.group(0).strip()
        lines = table_text.split("\n")
        # Remove separator rows (|---|---|)
        clean_lines = [l for l in lines if not re.match(r"^\|[\s\-:|]+\|$", l)]
        return "```\n" + "\n".join(clean_lines) + "\n```"

    result = re.sub(
        r"(?:^\|.+\|[ \t]*\n)+",
        _table_to_code,
        result,
        flags=re.MULTILINE,
    )

    # --- Phase 12: Blockquotes — clean up nested >> → > ---
    result = re.sub(r"^>+\s*", "> ", result, flags=re.MULTILINE)

    # --- Phase 13: Restore stashed code ---
    for i, block in enumerate(code_blocks):
        cleaned = re.sub(r"^```\w*\n?", "```\n", block, count=1)
        result = result.replace(f"{_CB}{i}\x00", cleaned)

    for i, code in enumerate(inline_codes):
        result = result.replace(f"{_IC}{i}\x00", code)

    # --- Phase 14: Clean up extra blank lines ---
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


@register(ContentType.MARKDOWN, TargetFormat.SLACK)
def md_to_slack(text: str) -> dict[str, str | None]:
    """Convert markdown to Slack mrkdwn. Written as plain text (Slack parses it)."""
    mrkdwn = _convert_md_to_mrkdwn(text)
    return {"html": None, "plain": mrkdwn}
