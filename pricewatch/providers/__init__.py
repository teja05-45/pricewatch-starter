"""LLM providers behind one tiny interface.

    provider.complete(system, user, metadata={"source_url": ...}, timeout=30) -> str

`metadata["source_url"]` is REQUIRED on every call: the grader's stub provider uses it to
decide what to answer, and logging/caching keys off it. Providers raise `ProviderTimeout`
or `ProviderError`; they never return partial output.

Select a provider with `--provider NAME` or `PRICEWATCH_PROVIDER=NAME`. If the env var
`PRICEWATCH_PROVIDER_PATH` points at a Python file exposing `make_provider()`, that file is
loaded instead of the built-ins (this is how the autograder injects its stub).
"""
from __future__ import annotations

import importlib.util
import os
from typing import Protocol


class ProviderError(Exception):
    pass


class ProviderTimeout(ProviderError):
    pass


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, metadata: dict, timeout: float = 30.0) -> str: ...


class EchoProvider:
    """Local stand-in so the pipeline runs without a key. Always answers 'no price found'."""

    name = "echo"

    def complete(self, system: str, user: str, *, metadata: dict, timeout: float = 30.0) -> str:
        assert "source_url" in metadata, "metadata.source_url is required"
        return '{"name": null, "price_cents": null, "currency": null, "availability": "unknown", "pack_size": 1, "compare_at_cents": null}'


def load_provider(name: str | None = None) -> Provider:
    try:
        import dotenv
        dotenv.load_dotenv()
    except ImportError:
        pass
    path = os.environ.get("PRICEWATCH_PROVIDER_PATH")
    if path:
        spec = importlib.util.spec_from_file_location("pw_injected_provider", path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.make_provider()
    name = name or os.environ.get("PRICEWATCH_PROVIDER", "echo")
    if name == "echo":
        return EchoProvider()
    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if name == "groq":
        from .groq_provider import GroqProvider
        return GroqProvider()
    if name in ("gemini", "google"):
        from .gemini_provider import GeminiProvider
        return GeminiProvider()
    raise ProviderError(f"unknown provider {name!r}")

