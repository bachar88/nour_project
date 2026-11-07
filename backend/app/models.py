"""Real model wrappers. Heavy libraries are imported lazily so the API and tests start without them.

Any object with the same methods can replace these (the tests use small fakes):
- Embedder.encode(texts) -> np.ndarray of L2-normalized vectors
- Reranker.score(query, texts) -> list[float] in [0, 1]
- LLM.complete(messages) -> (answer_text, total_tokens)
"""
from __future__ import annotations

import math

from .config import Settings


def _device(settings: Settings) -> str:
    if settings.device != "auto":
        return settings.device
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


class SentenceTransformerEmbedder:
    def __init__(self, settings: Settings):
        from sentence_transformers import SentenceTransformer
        device = _device(settings)
        self.model = SentenceTransformer(settings.embed_model, device=device)
        if device == "cuda":
            self.model.half()
        self.model.max_seq_length = 512  # chunks are short; the 8192 default only costs time

    def encode(self, texts: list[str]):
        return self.model.encode(texts, batch_size=64, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=len(texts) > 64)


class CrossEncoderReranker:
    """Reads (question, chunk) together and scores how well the chunk answers the question."""

    def __init__(self, settings: Settings):
        from sentence_transformers import CrossEncoder
        device = _device(settings)
        self.model = CrossEncoder(settings.rerank_model, device=device, max_length=512)
        if device == "cuda":
            self.model.model.half()

    def score(self, query: str, texts: list[str]) -> list[float]:
        scores = [float(s) for s in self.model.predict([(query, t) for t in texts], batch_size=32)]
        if any(s < 0 or s > 1 for s in scores):  # some versions return logits
            scores = [1 / (1 + math.exp(-s)) for s in scores]
        return scores


class GroqLLM:
    def __init__(self, settings: Settings):
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set (backend/.env)")
        from groq import Groq
        self.client = Groq(api_key=settings.groq_api_key, max_retries=5, timeout=60)
        self.settings = settings

    def complete(self, messages: list[dict]) -> tuple[str, int]:
        comp = self.client.chat.completions.create(
            model=self.settings.groq_model, messages=messages,
            temperature=self.settings.temperature, max_tokens=self.settings.max_tokens)
        tokens = comp.usage.total_tokens if comp.usage else 0
        return comp.choices[0].message.content.strip(), tokens
