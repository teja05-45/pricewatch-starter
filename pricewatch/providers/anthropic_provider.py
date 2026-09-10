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
        self.model = model or os.environ.get("PRICEWATCH_MODEL") or os.environ.get("ANTHROPIC_MODEL") or "claude-3-5-haiku-20241022"

    def complete(self, system: str, user: str, *, metadata: dict, timeout: float = 30.0) -> str:
        assert "source_url" in metadata
        import anthropic
        
        models_to_try = [self.model]
        for fb in ("claude-3-5-haiku-20241022", "claude-3-haiku-20240307"):
            if fb not in models_to_try:
                models_to_try.append(fb)

        last_exc: Exception | None = None
        for m_name in models_to_try:
            try:
                r = self.client.messages.create(
                    model=m_name, max_tokens=512, temperature=0, system=system, timeout=timeout,
                    messages=[{"role": "user", "content": user}],
                )
                return "".join(getattr(b, "text", "") for b in r.content)
            except anthropic.APITimeoutError as e:
                raise ProviderTimeout(str(e)) from e
            except anthropic.AnthropicError as e:
                last_exc = e
                if m_name != models_to_try[-1] and ("404" in str(e) or "not_found" in str(e)):
                    continue
                raise ProviderError(str(e)) from e
        if last_exc:
            raise ProviderError(str(last_exc))
        raise ProviderError("Anthropic complete failed")
