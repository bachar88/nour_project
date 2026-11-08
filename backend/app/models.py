"""Hosted model clients (plain HTTP, no torch): Cloudflare Workers AI for BGE-M3, Groq for answers.

Anything with the same methods can replace them (tests and demo mode use app/dev_fakes.py):
- Embedder.encode(texts) -> list of L2-normalized vectors (lists of floats)
- LLM.complete(messages) -> (answer_text, total_tokens)
"""
from __future__ import annotations

import math
import time

import httpx

from .config import Settings


def _l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


class CloudflareEmbedder:
    """BGE-M3 on Cloudflare Workers AI (free: 10,000 Neurons/day)."""
    MAX_BATCH = 100  # API limit per request

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        if not settings.cf_account_id or not settings.cf_api_token:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are not set")
        self.url = (f"https://api.cloudflare.com/client/v4/accounts/{settings.cf_account_id}"
                    f"/ai/run/{settings.cf_embed_model}")
        self.http = client or httpx.Client(timeout=60, headers={"Authorization": f"Bearer {settings.cf_api_token}"})
        self.dim = settings.embed_dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.MAX_BATCH):
            batch = texts[i:i + self.MAX_BATCH]
            r = _post_with_retry(self.http, self.url, {"text": batch, "truncate_inputs": True})
            body = r.json()
            if not body.get("success", True) or "result" not in body:
                raise RuntimeError(f"Cloudflare AI error: {body.get('errors')}")
            data = body["result"]["data"]
            if len(data) != len(batch) or (data and len(data[0]) != self.dim):
                raise RuntimeError(f"Unexpected embedding shape from Cloudflare: {body['result'].get('shape')}")
            out.extend(_l2_normalize(v) for v in data)
        return out


class GroqLLM:
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self.s = settings
        self.http = client or httpx.Client(timeout=90, headers={"Authorization": f"Bearer {settings.groq_api_key}"})

    def complete(self, messages: list[dict]) -> tuple[str, int]:
        payload = {"model": self.s.groq_model, "messages": messages,
                   "temperature": self.s.temperature, "max_completion_tokens": self.s.max_tokens}
        if self.s.groq_model.startswith("openai/gpt-oss"):
            # Reasoning model: keep the thinking short and leave it out of the reply, so parse_answer only
            # sees «الجواب: … الدليل: «…»». (Groq: `reasoning_format` is not supported for GPT-OSS;
            # `include_reasoning` is.) Thinking still counts in usage and in max_completion_tokens.
            payload["reasoning_effort"] = self.s.reasoning_effort
            payload["include_reasoning"] = False
        body = _post_with_retry(self.http, self.URL, payload).json()
        choice = body["choices"][0]
        text = (choice["message"].get("content") or "").strip()
        if not text:
            if choice.get("finish_reason") == "length":
                raise RuntimeError("النموذج استهلك حدّ الرموز في التفكير قبل أن يجيب "
                                   "(زد MAX_TOKENS أو خفّض REASONING_EFFORT).")
            raise RuntimeError("لم يُرجع النموذج أي جواب.")
        return text, body.get("usage", {}).get("total_tokens", 0)


def _post_with_retry(http: httpx.Client, url: str, payload: dict, tries: int = 3) -> httpx.Response:
    """POST with a short back-off on 429 (rate limit) and 5xx."""
    for attempt in range(tries):
        r = http.post(url, json=payload)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt < tries - 1:
                wait = float(r.headers.get("retry-after", 0) or 0) or 1.5 * (attempt + 1)
                time.sleep(min(wait, 8))
                continue
            if r.status_code == 429:
                raise RuntimeError("الخدمة مشغولة حاليًا (تجاوز حد الطلبات)، أعد المحاولة بعد دقيقة.")
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} from {httpx.URL(url).host}: {r.text[:300]}")
        return r
    raise RuntimeError("unreachable")
