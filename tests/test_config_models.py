"""Model picker choices."""

from smartpaste.config import AVAILABLE_MODELS, DEFAULT_MODEL, model_choices


def test_default_model_is_listed():
    assert DEFAULT_MODEL in AVAILABLE_MODELS


def test_saved_model_not_in_list_is_kept():
    ids = [m for m, _ in model_choices("claude-haiku-4-5-20251001")]
    assert ids[-1] == "claude-haiku-4-5-20251001"
    assert set(AVAILABLE_MODELS) <= set(ids)


def test_fetched_models_are_merged_without_duplicates():
    fetched = {"claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-new-6": "Claude New 6"}
    ids = [m for m, _ in model_choices(DEFAULT_MODEL, fetched)]
    assert ids.count("claude-sonnet-5-5") == 1
    assert "claude-new-6" in ids
