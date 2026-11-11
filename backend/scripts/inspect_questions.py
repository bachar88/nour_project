"""Look at what the RAG does for a list of questions: the chunks it retrieves, which ones it
sends to the model, and (optionally) the answer. Read-only: nothing is written anywhere.

In the admin notebook:
    from scripts.inspect_questions import make_engine, show_retrieval, show_answers
    engine = make_engine(with_llm=False)            # retrieval only: no Groq calls
    show_retrieval(engine, QUESTIONS)
    engine = make_engine(with_llm=True)
    show_answers(engine, QUESTIONS)                 # ≈2,000 Groq tokens per question

Command line (one question per line in a .txt file):
    python -m scripts.inspect_questions questions.txt [--llm] [--top 5]
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time

from app.chunking import corpus_from_units
from app.config import settings
from app.rag import RagEngine

LINE = "─" * 90


def make_engine(with_llm: bool = False) -> RagEngine:
    """Same pieces as the site: units + vectors from Supabase, BGE-M3 from Cloudflare, Groq if asked."""
    from app.models import CloudflareEmbedder, GroqLLM
    from app.store import SupabaseStore
    store = SupabaseStore(settings)
    return RagEngine(corpus_from_units(store.load_units()), settings, CloudflareEmbedder(settings),
                     store, GroqLLM(settings) if with_llm else None)


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "…"


def show_retrieval(engine: RagEngine, questions: list[str], top: int = 5, madhhab: str = "maliki",
                   preview: int = 140, full_passages: bool = True) -> list[dict]:
    """For each question: the `top` closest chunks (score, book, bab, section, start of text),
    whether the score gate lets it through, and the passages actually sent to the model."""
    s = engine.settings
    # Gate OFF so we always see the candidates; the real gate decision is printed separately.
    open_engine = RagEngine(engine.corpus, dataclasses.replace(s, min_cosine_score=-1.0),
                            engine.embedder, engine.store, engine.llm)
    print(f"Settings: MIN_COSINE_SCORE={s.min_cosine_score}  COSINE_MARGIN={s.cosine_margin}  "
          f"MAX_K={s.max_k}  MAX_CONTEXT_CHARS={s.max_context_chars}")
    report = []
    for n, q in enumerate(questions, 1):
        r = open_engine.retrieve(q, madhhab)
        cands, passages = r["candidates"], r["passages"]
        best = cands[0]["score"] if cands else 0.0
        gated = best < s.min_cosine_score
        sent_units = {p["metadata"]["unit_key"] for p in passages}
        # same rule as RagEngine.select_context: within COSINE_MARGIN of the best, at most MAX_K
        kept = len([c for c in cands if c["score"] >= best - s.cosine_margin][:s.max_k])
        print(f"\n{LINE}\n[{n}] {q}")
        print(f"    best score {best:.3f} → " + ("BLOCKED by MIN_COSINE_SCORE: the site would refuse "
              "without asking the model" if gated else f"{len(passages)} passage(s) sent to the model"))
        for i, c in enumerate(cands[:top], 1):
            m = c["metadata"]
            mark = "→ sent" if (not gated and i <= kept and m["unit_key"] in sent_units) else "      "
            section = "" if m["section"] == m["bab_title"] else f" | {_clip(m['section'], 30)}"
            print(f"    {i}. {c['score']:.3f} {mark}  {m['book']} | {_clip(m['bab_title'], 35)}{section}")
            print(f"           {_clip(c['text'], preview)}")
        if full_passages and not gated:
            for i, p in enumerate(passages, 1):
                print(f"    ── passage [{i}] sent ({len(p['text'])} chars): {p['metadata']['book']} — "
                      f"{p['metadata']['bab_title']}\n       {p['text']}")
        report.append({"question": q, "best_score": round(best, 4), "gated": gated,
                       "sent": [p["metadata"]["unit_key"] for p in passages]})
    blocked = [x for x in report if x["gated"]]
    print(f"\n{LINE}\n{len(questions)} questions | blocked by the gate: {len(blocked)} | "
          f"best scores: min {min(x['best_score'] for x in report):.3f}, "
          f"max {max(x['best_score'] for x in report):.3f}")
    return report


def show_answers(engine: RagEngine, questions: list[str], madhhab: str = "maliki",
                 sleep: float = 15.0) -> list[dict]:
    """The full pipeline, exactly as the site runs it (gate on). Paced for Groq's free limits."""
    if engine.llm is None:
        raise ValueError("make_engine(with_llm=True) is needed for answers")
    results = []
    for n, q in enumerate(questions, 1):
        r = engine.ask(q, madhhab)
        print(f"\n{LINE}\n[{n}] {q}")
        print(f"    abstained={r['abstained']}  grounding={r['grounding']}  tokens={r['tokens']}  "
              f"top_score={r['top_score']}  corrections_used={r.get('corrections_used', [])}")
        print(f"    الجواب: {r['answer']}")
        for ev in r["evidence"]:
            print(f"    {'✓' if ev['found'] else '✗ NOT IN TEXT'} «{ev['quote']}» [{ev['passage']}]")
        results.append(r)
        if n < len(questions):
            time.sleep(sleep)  # stay under Groq's free 8,000 tokens/minute
    return results


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("file", help="text file, one question per line")
    p.add_argument("--llm", action="store_true", help="also generate answers (Groq)")
    p.add_argument("--top", type=int, default=5)
    args = p.parse_args(argv)
    with open(args.file, encoding="utf-8") as f:
        questions = [line.strip() for line in f if line.strip()]
    engine = make_engine(with_llm=args.llm)
    show_retrieval(engine, questions, top=args.top)
    if args.llm:
        show_answers(engine, questions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
