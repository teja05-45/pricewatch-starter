import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from pricewatch.agents.llm_extractor import extract_with_llm, parse_llm_json
from pricewatch.evaluate import run
from pricewatch.providers import (
    EchoProvider,
    ProviderError,
    ProviderTimeout,
    load_provider,
)
from pricewatch.providers.anthropic_provider import AnthropicProvider
from pricewatch.providers.openai_provider import OpenAIProvider
from pricewatch.providers.groq_provider import GroqProvider
from pricewatch.providers.gemini_provider import GeminiProvider


def test_echo_provider():
    p = EchoProvider()
    res = p.complete("sys", "user", metadata={"source_url": "http://example.com"})
    assert "price_cents" in res


def test_load_provider_echo():
    p = load_provider("echo")
    assert p.name == "echo"


def test_provider_requires_source_url():
    p = EchoProvider()
    with pytest.raises(AssertionError):
        p.complete("sys", "user", metadata={})


def test_anthropic_provider_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ProviderError):
            AnthropicProvider()


def test_anthropic_provider_with_only_anthropic_key():
    """Proves AnthropicProvider instantiates and respects PRICEWATCH_MODEL with ONLY ANTHROPIC_API_KEY set."""
    mock_anthropic = MagicMock()
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test12345", "PRICEWATCH_MODEL": "claude-3-5-sonnet-20241022"}, clear=True), \
         patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        p = AnthropicProvider()
        assert p.name == "anthropic"
        assert p.model == "claude-3-5-sonnet-20241022"


def test_anthropic_provider_complete_mocked():
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_msg_content = [MagicMock(text='{"name": "Test Product", "price_cents": 2999, "currency": "USD", "availability": "in_stock", "pack_size": 1}')]
    mock_response = MagicMock(content=mock_msg_content)
    mock_client.messages.create.return_value = mock_response
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test12345"}, clear=True), \
         patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        p = AnthropicProvider()
        res = p.complete("sys prompt", "user prompt", metadata={"source_url": "http://example.com/p1"})
        assert "price_cents" in res
        assert "2999" in res


def test_openai_provider_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ProviderError):
            OpenAIProvider()


def test_groq_provider_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ProviderError):
            GroqProvider()


def test_gemini_provider_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ProviderError):
            GeminiProvider()


def test_google_provider_registration():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123"}):
        p = load_provider("google")
        assert p.name == "google"


def test_google_provider_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
            GeminiProvider()


def test_google_provider_pricewatch_model_honored():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123", "PRICEWATCH_MODEL": "gemini-2.5-flash"}, clear=True):
        p = load_provider("google")
        assert p.model == "gemini-2.5-flash"


def test_google_provider_successful_structured_json_response():
    mock_genai = MagicMock()
    mock_model = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"name": "Test Product", "price_cents": 2999, "currency": "USD", "availability": "in_stock", "pack_size": 1}'
    mock_model.generate_content.return_value = mock_resp
    mock_genai.GenerativeModel.return_value = mock_model

    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123"}), \
         patch("pricewatch.providers.gemini_provider.HAS_GENAI", True), \
         patch("pricewatch.providers.gemini_provider.genai", mock_genai, create=True):
        p = load_provider("google")
        res = p.complete("system instruction", "user content", metadata={"source_url": "http://example.com/test"})
        assert "Test Product" in res
        assert "2999" in res


def test_google_provider_requires_source_url():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123"}):
        p = load_provider("google")
        with pytest.raises(AssertionError):
            p.complete("system instruction", "user content", metadata={})


def test_google_provider_error_handling():
    mock_genai = MagicMock()
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = Exception("API Quota Exceeded 429")
    mock_genai.GenerativeModel.return_value = mock_model

    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123"}), \
         patch("pricewatch.providers.gemini_provider.HAS_GENAI", True), \
         patch("pricewatch.providers.gemini_provider.genai", mock_genai, create=True), \
         patch("time.sleep"):
        p = load_provider("google")
        with pytest.raises(ProviderError):
            p.complete("system instruction", "user content", metadata={"source_url": "http://example.com/test"})





def test_provider_injection_via_env(tmp_path):
    """Test provider injection contract via PRICEWATCH_PROVIDER_PATH."""
    dummy_module_code = """
class InjectedProvider:
    name = "injected_stub"
    model = "custom-v1"
    def complete(self, system, user, *, metadata, timeout=30.0):
        assert "source_url" in metadata
        return '{"name": "Injected Product", "price_cents": 5500, "currency": "USD", "availability": "in_stock", "pack_size": 1}'

def make_provider():
    return InjectedProvider()
"""
    provider_file = tmp_path / "custom_provider.py"
    provider_file.write_text(dummy_module_code, encoding="utf-8")

    with patch.dict(os.environ, {"PRICEWATCH_PROVIDER_PATH": str(provider_file)}):
        p = load_provider()
        assert p.name == "injected_stub"
        res = p.complete("sys", "user", metadata={"source_url": "http://example.com/item"})
        assert "Injected Product" in res


def test_llm_json_parsing_and_markdown_code_fences():
    raw_markdown = """```json
    {
      "name": "Nordkart Fleece Jacket",
      "price_cents": 129900,
      "currency": "NOK",
      "availability": "in_stock",
      "pack_size": 1,
      "compare_at_cents": null
    }
    ```"""
    parsed = parse_llm_json(raw_markdown)
    assert parsed["name"] == "Nordkart Fleece Jacket"
    assert parsed["price_cents"] == 129900

    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("This is raw text without json")


def test_llm_extractor_jpy_zero_decimal_currency():
    mock_provider = MagicMock()
    mock_provider.complete.return_value = '{"name": "Tokyo Headphones", "price_cents": 1500, "currency": "JPY", "availability": "in_stock", "pack_size": 1}'

    obs = extract_with_llm(mock_provider, "tokyo_store", "http://example.com/tokyo/item1", "<html>Tokyo Headphones 1500 JPY</html>")
    assert obs.price_cents == 1500
    assert obs.currency == "JPY"


def test_llm_extractor_european_price_formatting_fallback():
    mock_provider = MagicMock()
    mock_provider.complete.return_value = '{"name": "Berlin Chair", "price_cents": 72092, "currency": "EUR", "availability": "in_stock", "pack_size": 1}'

    obs = extract_with_llm(mock_provider, "berlin_store", "http://example.com/berlin/item2", "<html>Berlin Chair 720,92 €</html>")
    assert obs.price_cents == 72092
    assert obs.currency == "EUR"


class FaultInjectingProvider:
    name = "fault_stub"
    model = "stub-v1"

    def complete(self, system: str, user: str, *, metadata: dict, timeout: float = 30.0) -> str:
        url = metadata.get("source_url", "")
        if "nk-000" in url:
            raise ProviderTimeout("Simulated timeout")
        if "nk-001" in url:
            return "THIS IS NOT VALID JSON"
        if "nk-002" in url:
            raise ProviderError("Simulated API failure")
        return '{"name": "Valid Product", "price_cents": 1000, "currency": "NOK", "availability": "in_stock", "pack_size": 1}'


def test_eval_harness_survives_fault_injection(tmp_path):
    p = FaultInjectingProvider()
    out_dir = tmp_path / "out"
    report = run(p, "eval/snapshots", "eval/labels.json", out_dir)

    assert report["n"] == 90
    assert report["errors"]["timeout"] >= 1
    assert report["errors"]["malformed_output"] >= 1
    assert report["errors"]["provider_error"] >= 1
    assert (out_dir / "report.json").exists()
    assert (out_dir / "label_issues.json").exists()


def test_eval_harness_caching_and_hit(tmp_path):
    p = FaultInjectingProvider()
    out_dir = tmp_path / "cache_test_out"

    # First run (cache miss)
    report1 = run(p, "eval/snapshots", "eval/labels.json", out_dir)

    # Second run (cache hit)
    with patch.object(p, "complete", side_effect=Exception("Should not be called due to cache hit")):
        report2 = run(p, "eval/snapshots", "eval/labels.json", out_dir)

    assert report1["n"] == report2["n"]
    assert report2["n"] == 90
