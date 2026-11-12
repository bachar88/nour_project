"""Lightweight stand-ins for the hosted services (no network, no API key, no database).
Used by the tests and by demo mode: NOUR_DEMO=1 uvicorn app.main:app
Answers in demo mode are NOT real — they only quote retrieved text to exercise the UI."""
from __future__ import annotations

import dataclasses
import hashlib
import math

from .chunking import Corpus, build_corpus, normalize_ar
from .config import Settings

DIM = 512


class FakeEmbedder:
    """Bag of character trigrams hashed into 512 dims, L2-normalized (pure Python)."""
    def encode(self, texts):
        out = []
        for t in texts:
            v = [0.0] * DIM
            t = normalize_ar(t)
            for j in range(len(t) - 2):
                v[int(hashlib.md5(t[j:j + 3].encode()).hexdigest(), 16) % DIM] += 1
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class MemoryStore:
    """Same .match() contract as SupabaseStore, over chunks held in memory."""
    def __init__(self, corpus: Corpus, embedder):
        self.rows = [{"id": c.id, "unit_key": c.metadata["unit_key"], "madhhab": c.metadata["madhhab"],
                      "seg_start": c.metadata["seg_start"], "seg_end": c.metadata["seg_end"], "text": c.text}
                     for c in corpus.chunks]
        self.vecs = embedder.encode([c.embed_text for c in corpus.chunks])
        self.calls = 0

    def match(self, embedding, madhhab, count):
        self.calls += 1
        scored = [dict(r, similarity=sum(a * b for a, b in zip(embedding, v)))
                  for r, v in zip(self.rows, self.vecs) if r["madhhab"] == madhhab]
        return sorted(scored, key=lambda r: -r["similarity"])[:count]

    def ping(self):
        return True

    # learning-loop tables, kept in memory (demo mode / tests)
    def insert(self, table, row):
        self.tables = getattr(self, "tables", {})
        rows = self.tables.setdefault(table, [])
        row = dict(row, id=len(rows) + 1)
        rows.append(row)
        return row

    def select(self, table, **params):
        return list(getattr(self, "tables", {}).get(table, []))

    def match_corrections(self, embedding, madhhab, count):
        rows = [r for r in getattr(self, "tables", {}).get("corrections", []) if r["madhhab"] == madhhab]
        scored = [dict(r, similarity=sum(a * b for a, b in zip(embedding, r["embedding"]))) for r in rows]
        return sorted(scored, key=lambda r: -r["similarity"])[:count]


class FakeLLM:
    """mode='quote': quotes 12 words of passage [1]; 'invent': quotes text that is not there;
    'abstain': returns the abstention sentence."""
    def __init__(self, mode="quote"):
        self.mode = mode
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        user = messages[-1]["content"]
        first = user.split("[1]", 1)[1].split(")\n", 1)[1].split("\n\n")[0]
        if self.mode == "abstain":
            return "لم يرد في النص ما يجيب عن هذا السؤال.", 10
        if self.mode == "invent":
            return "الجواب: حكم مخترع.\nالدليل: «هذا كلام غير موجود في المقطع أصلا» [1]", 50
        quote = " ".join(first.split()[:12])
        return (f"الجواب: (وضع تجريبي) هذا جواب مولَّد آليًا من المقطع الأول دون نموذج لغوي.\n"
                f"الدليل: «{quote}» [1]"), 50


# Trigram vectors give lower cosine scores than BGE-M3, so demo mode uses looser thresholds.
DEMO_OVERRIDES = {"min_cosine_score": 0.2, "cosine_margin": 0.08}


def demo_engine(settings: Settings, llm_mode: str = "quote"):
    from .rag import RagEngine
    s = dataclasses.replace(settings, **DEMO_OVERRIDES)
    corpus = build_corpus(s)  # from backend/data/*.txt
    emb = FakeEmbedder()
    return RagEngine(corpus, s, emb, MemoryStore(corpus, emb), FakeLLM(llm_mode))
