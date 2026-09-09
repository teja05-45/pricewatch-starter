from __future__ import annotations

import os

from . import ProviderError, ProviderTimeout


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise ProviderError("pip install anthropic") from e
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ProviderError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("PRICEWATCH_MODEL", "claude-haiku-4-5")

    def complete(self, system: str, user: str, *, metadata: dict, timeout: float = 30.0) -> str:
        assert "source_url" in metadata
        import anthropic
        try:
            r = self.client.messages.create(
                model=self.model, max_tokens=512, temperature=0, system=system, timeout=timeout,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APITimeoutError as e:
            raise ProviderTimeout(str(e)) from e
        except anthropic.AnthropicError as e:
            raise ProviderError(str(e)) from e
        return "".join(getattr(b, "text", "") for b in r.content)
