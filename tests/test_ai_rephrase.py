"""Result handling for AI rephrase (no network)."""

from types import SimpleNamespace

import pytest

from smartpaste.ai_rephrase import _request_kwargs, collect_result


def _msg(stop_reason, *texts):
    blocks = [SimpleNamespace(type="thinking", thinking="")]
    blocks += [SimpleNamespace(type="text", text=t) for t in texts]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def test_joins_all_text_blocks():
    result = collect_result(_msg("end_turn", "Hello ", "world"))
    assert result.text == "Hello world"
    assert not result.truncated


def test_flags_max_tokens_as_truncated():
    assert collect_result(_msg("max_tokens", "partial")).truncated


def test_refusal_raises():
    with pytest.raises(RuntimeError):
        collect_result(_msg("refusal"))


def test_effort_only_sent_to_models_that_accept_it():
    assert _request_kwargs("claude-haiku-5-5", "", "x")["output_config"] == {"effort": "low"}
    assert "output_config" not in _request_kwargs("claude-haiku-4-5-20251001", "", "x")
