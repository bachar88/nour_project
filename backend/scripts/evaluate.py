"""Measure retrieval on the Salat test set against the real index, and suggest thresholds.

    python -m scripts.evaluate          # retrieval only: no Groq calls (fast, free)
    python -m scripts.evaluate --llm    # also generate answers (≈2,000 Groq tokens per question)

Reads: Hit = the right text is in the passages sent to the LLM; top = best cosine score.
The out-of-scope questions should score LOWER than the in-scope ones: the gap gives MIN_COSINE_SCORE.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time

from app.chunking import corpus_from_units, normalize_ar
from app.config import settings
from app.rag import RagEngine

EXPECTED = {
    "ما هي فرائض الصلاة؟": ["فرائض الصلاة"],
    "ما هو الوقت المختار لصلاة العصر؟": ["للعصر من القامة", "ان الوقت فيها ما لم تصفر الشمس"],
    "متى يكون سجود السهو قبل السلام؟": ["فللنقصان سجدتان قبل السلام", "ينقص فليسجد له قبل السلام"],
    "ما حكم من ضحك في الصلاة؟": ["ضحك في الصلاة"],
    "كم عدد سجدات القرآن؟": ["احدى عشرة سجدة"],
    "ما هي مسافة قصر الصلاة للمسافر؟": ["اربعة برد"],
    "كم يكبر في الركعة الأولى من صلاة العيد؟": ["يكبر في الاولى سبعا"],
    "ما هي عورة الرجل في الصلاة؟": ["ما بين السرة والركبة"],
    "ما حكم الأذان؟": ["والاذان واجب"],
    "ماذا يفعل من شك هل صلى ثلاثا أم أربعا؟": ["بنى على اليقين", "الشك في النقصان كتحققه"],
    "ماذا يفعل من قام من اثنتين ولم يجلس للتشهد؟": ["قام من اثنتين", "قام من ركعتين قبل الجلوس"],
    "كم عدد التكبيرات في صلاة الجنازة؟": ["اربع تكبيرات"],
}
OUT_OF_SCOPE = ["ما حكم زكاة الذهب؟", "ما هي أركان الحج؟", "ما حكم صيام يوم عرفة؟"]


def hit(question, passages):
    kws = EXPECTED.get(question)
    if not kws:
        return None
    ctx = normalize_ar(" ".join(p["text"] for p in passages))
    return any(normalize_ar(k) in ctx for k in kws)


def main(argv=None, engine=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--llm", action="store_true", help="also call Groq for answers")
    args = p.parse_args(argv)

    if engine is None:
        from app.models import CloudflareEmbedder, GroqLLM
        from app.store import SupabaseStore
        store = SupabaseStore(settings)
        llm = GroqLLM(settings) if args.llm else None
        engine = RagEngine(corpus_from_units(store.load_units()), settings,
                           CloudflareEmbedder(settings), store, llm)
    # Evaluate selection with the gate OFF, so we see every question's best score
    open_engine = RagEngine(engine.corpus, dataclasses.replace(engine.settings, min_cosine_score=-1.0),
                            engine.embedder, engine.store, engine.llm)

    rows = []
    for q in list(EXPECTED) + OUT_OF_SCOPE:
        r = open_engine.retrieve(q, "maliki")
        top = r["candidates"][0]["score"] if r["candidates"] else 0.0
        cand_hit = hit(q, r["candidates"])
        rows.append((q, top, hit(q, r["passages"]), cand_hit, len(r["passages"])))

    print(f"{'question':48s} {'top':>6s}  hit  in-top-{settings.fetch_k}  n")
    for q, top, h, ch, n in rows:
        tag = "OOS " if q in OUT_OF_SCOPE else "    "
        print(f"{tag}{q[:44]:44s} {top:6.3f}  {'-' if h is None else ('yes' if h else 'NO '):4s} "
              f"{'-' if ch is None else ('yes' if ch else 'NO '):10s} {n}")

    ins = [t for q, t, *_ in rows if q in EXPECTED]
    oos = [t for q, t, *_ in rows if q in OUT_OF_SCOPE]
    hits = [h for q, _, h, *_ in rows if q in EXPECTED]
    print(f"\nHit in context: {sum(hits)}/{len(hits)}   |   in-scope top scores: min {min(ins):.3f}"
          f"   |   out-of-scope top scores: max {max(oos):.3f}")
    if min(ins) > max(oos):
        print(f"→ Suggested MIN_COSINE_SCORE ≈ {(min(ins) + max(oos)) / 2:.3f} (midpoint of the gap). "
              f"Current: {settings.min_cosine_score}")
    else:
        print("→ No clean gap between in-scope and out-of-scope scores: keep MIN_COSINE_SCORE near "
              f"{max(oos):.3f} and let the model's abstention handle the rest.")

    if args.llm and engine.llm is not None:
        print("\nAnswers:")
        for q in list(EXPECTED) + OUT_OF_SCOPE:
            r = engine.ask(q)
            print(f"- {q}\n  abstained={r['abstained']} grounding={r['grounding']} tokens={r['tokens']}\n"
                  f"  {r['raw'][:300] or r['answer']}")
            time.sleep(15)  # stay under Groq's free 8,000 tokens/minute
    return 0


if __name__ == "__main__":
    sys.exit(main())
