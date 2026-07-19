"""LLM adapter: provider selection and graceful degradation."""

from app import llm


def test_no_keys_means_rules_only(monkeypatch) -> None:
    for var in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert llm.provider() is None


def test_explicit_off_wins_over_keys(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert llm.provider() is None


def test_anthropic_autodetected_from_key(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert llm.provider() == "anthropic"


def test_gemini_preferred_when_both_keys_present(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert llm.provider() == "gemini"


def test_provider_without_key_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.provider() is None


def test_polish_without_provider_returns_draft(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "none")
    message, source = llm.polish("Draft answer.", "user text", "en")
    assert (message, source) == ("Draft answer.", "rules")


def test_polish_survives_provider_failure(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm, "_call_anthropic", boom)
    message, source = llm.polish("Draft answer.", "user text", "en")
    assert (message, source) == ("Draft answer.", "rules")
