from __future__ import annotations

import os
import time
import requests

from . import ProviderError, ProviderTimeout

FALLBACK_GROQ_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]


class GroqProvider:
    name = "groq"

    def __init__(self, model: str | None = None):
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise ProviderError("GROQ_API_KEY not set")
        self.key = key
        groq_model = os.environ.get("GROQ_MODEL")
        env_model = os.environ.get("PRICEWATCH_MODEL")
        
        self.model = model or groq_model or env_model or "openai/gpt-oss-20b"

    def complete(self, system: str, user: str, *, metadata: dict, timeout: float = 30.0) -> str:
        assert "source_url" in metadata, "metadata.source_url is required"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

        models_to_try = [self.model] + [m for m in FALLBACK_GROQ_MODELS if m != self.model]

        for model_candidate in models_to_try:
            payload = {
                "model": model_candidate,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.0,
                "max_tokens": 512,
            }
            for attempt in range(3):
                try:
                    r = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=timeout,
                    )
                    if r.status_code == 429:
                        if attempt < 2:
                            time.sleep(3.0 * (attempt + 1))
                            continue
                        # If rate limited on this model candidate, break out and try next model candidate
                        break
                    if r.status_code != 200:
                        break
                    data = r.json()
                    res_text = data["choices"][0]["message"]["content"] or ""
                    time.sleep(1.0)
                    return res_text
                except requests.Timeout as e:
                    raise ProviderTimeout(str(e)) from e
                except requests.RequestException:
                    if attempt < 2:
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    break

        raise ProviderError("Groq API error: all candidate models rate limited or failed")
