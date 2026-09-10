from __future__ import annotations

import os
import json
import time
import requests
from typing import Any

from . import ProviderError, ProviderTimeout

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


EXTRACTION_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "price_cents": {"type": "INTEGER", "nullable": True},
        "currency": {"type": "STRING", "nullable": True},
        "availability": {
            "type": "STRING",
            "enum": ["in_stock", "out_of_stock", "unknown"],
            "nullable": True,
        },
        "pack_size": {"type": "INTEGER", "nullable": True},
        "price_reason": {"type": "STRING", "nullable": True},
    },
    "required": ["price_cents", "currency", "availability", "pack_size"],
}


class GeminiProvider:
    name = "google"

    def __init__(self, model: str | None = None):
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ProviderError("GEMINI_API_KEY not set")
        self.key = key
        
        env_model = os.environ.get("PRICEWATCH_MODEL") or os.environ.get("GEMINI_MODEL")
        self.model = model or env_model or "gemini-2.5-flash"
        
        if HAS_GENAI:
            try:
                genai.configure(api_key=self.key)
            except Exception:
                pass

    def complete(self, system: str, user: str, *, metadata: dict, timeout: float = 30.0) -> str:
        assert "source_url" in metadata, "metadata.source_url is required"

        for attempt in range(6):
            try:
                # Try official SDK first if available
                if HAS_GENAI:
                    try:
                        m = genai.GenerativeModel(
                            model_name=self.model,
                            system_instruction=system,
                            generation_config=genai.GenerationConfig(
                                response_mime_type="application/json",
                                response_schema=EXTRACTION_RESPONSE_SCHEMA,
                                temperature=0.0,
                                max_output_tokens=512,
                            ),
                        )
                        resp = m.generate_content(user, request_options={"timeout": timeout})
                        res_text = resp.text or ""
                        return res_text
                    except Exception as sdk_err:
                        err_str = str(sdk_err).lower()
                        if "timeout" in err_str or "timed out" in err_str:
                            raise ProviderTimeout(str(sdk_err)) from sdk_err
                        if "429" in err_str or "quota" in err_str or "resourceexhausted" in err_str:
                            if attempt < 5:
                                sleep_time = 15.0 * (attempt + 1)
                                time.sleep(sleep_time)
                                continue
                            raise ProviderError(f"Gemini API rate limit: {sdk_err}") from sdk_err
                        raise ProviderError(f"Gemini API error: {sdk_err}") from sdk_err

                # REST API fallback
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}"
                headers = {"Content-Type": "application/json"}
                payload: dict[str, Any] = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": f"System Instruction:\n{system}\n\nUser Prompt:\n{user}"}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.0,
                        "maxOutputTokens": 512,
                        "responseMimeType": "application/json",
                        "responseSchema": EXTRACTION_RESPONSE_SCHEMA,
                    },
                }

                r = requests.post(url, json=payload, headers=headers, timeout=timeout)
                if r.status_code == 429:
                    if attempt < 5:
                        retry_after = r.headers.get("retry-after")
                        sleep_secs = float(retry_after) if retry_after else (15.0 * (attempt + 1))
                        time.sleep(sleep_secs)
                        continue
                    raise ProviderError(f"Gemini API 429 rate limit: {r.text}")
                if r.status_code != 200:
                    raise ProviderError(f"Gemini API error HTTP {r.status_code}: {r.text}")

                data = r.json()
                try:
                    res_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return res_text
                except (KeyError, IndexError) as e:
                    raise ProviderError(f"Gemini API unexpected JSON payload: {r.text}") from e

            except requests.Timeout as e:
                raise ProviderTimeout(str(e)) from e
            except requests.RequestException as e:
                if attempt < 5:
                    time.sleep(5.0 * (attempt + 1))
                    continue
                raise ProviderError(str(e)) from e

        raise ProviderError("Gemini API call failed after retries")


GoogleProvider = GeminiProvider

