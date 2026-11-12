"""The exam: run the golden test set (eval/golden.jsonl) against the real index and score it.

    python -m scripts.evaluate                          # retrieval only: no Groq calls (fast, free)
    python -m scripts.evaluate --llm                    # also answers (≈2,000 Groq tokens/question, ~4 min)
    python -m scripts.evaluate --llm --save --label "prompt v2, effort medium"   # keep the scores in Supabase

Scores
- retrieval_hit: an expected sentence is in the passages sent to the model (retrieval did its job)
- evidence_hit:  the model QUOTED an expected sentence — needs learning.evidence_matches (your function).
                 This is what catches "right passage, wrong sentence".
- abstain_ok:    out-of-scope questions were refused
- grounded:      every quote really exists in the passages (no invented quotes)
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path

from app import learning
from app.chunking import corpus_from_units, find_quote_spans
from app.config import settings
from app.rag import SYSTEM_PROMPT, RagEngine

GOLDEN = Path(__file__).resolve().parents[1] / "eval" / "golden.jsonl"


def load_golden(path: Path = GOLDEN) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def groups(case: dict) -> list[list[str]]:
    """Expected evidence as groups: EVERY group must be covered, ANY sentence of a group covers it.
    - "expected_evidence": [a, b]           → one group: a OR b   (simple questions)
    - "expected_groups": [[list], [r1, r2]] → list AND (r1 OR r2) (answers that combine passages)"""
    return case.get("expected_groups") or [case["expected_evidence"]]


def retrieval_hit(case: dict, passages: list[dict]) -> bool | None:
    if case.get("out_of_scope"):
        return None
    return all(any(find_quote_spans(p["text"], e) for p in passages for e in g) for g in groups(case))


def evidence_hit(case: dict, quotes: list[str]) -> bool | None:
    """True if the model's quotes cover every expected group (uses learning.evidence_matches)."""
    if case.get("out_of_scope"):
        return None
    return all(any(learning.evidence_matches(q, e) for q in quotes for e in g) for g in groups(case))


def pct(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(100 * sum(vals) / len(vals), 1) if vals else None


def main(argv=None, engine=None, store=None, sleep: float = 15.0) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--llm", action="store_true", help="also call Groq for answers")
    p.add_argument("--save", action="store_true", help="store the run in the Supabase eval_runs table")
    p.add_argument("--label", default="", help="a name for this run, e.g. 'prompt v2'")
    args = p.parse_args(argv)

    if engine is None:
        from app.models import CloudflareEmbedder, GroqLLM
        from app.store import SupabaseStore
        store = SupabaseStore(settings)
        engine = RagEngine(corpus_from_units(store.load_units()), settings, CloudflareEmbedder(settings),
                           store, GroqLLM(settings) if args.llm else None)
    store = store or engine.store
    cases = load_golden()

    # 1) Retrieval, with the score gate OFF so every question shows its best score
    open_engine = RagEngine(engine.corpus, dataclasses.replace(engine.settings, min_cosine_score=-1.0),
                            engine.embedder, engine.store, engine.llm)
    details = []
    for case in cases:
        r = open_engine.retrieve(case["question"], case.get("madhhab", "maliki"))
        top = r["candidates"][0]["score"] if r["candidates"] else 0.0
        details.append({"question": case["question"], "out_of_scope": bool(case.get("out_of_scope")),
                        "top_score": round(top, 4), "retrieval_hit": retrieval_hit(case, r["passages"])})

    # 2) Answers (optional)
    scoring_written = True
    if args.llm and engine.llm is not None:
        for case, d in zip(cases, details):
            r = engine.ask(case["question"], case.get("madhhab", "maliki"))
            quotes = [ev["quote"] for ev in r["evidence"]]
            d.update(abstained=r["abstained"], grounding=r["grounding"], quotes=quotes,
                     answer=r["answer"], tokens=r["tokens"], corrections_used=r.get("corrections_used", []),
                     abstain_ok=bool(r["abstained"]) if case.get("out_of_scope") else None)
            try:
                d["evidence_hit"] = evidence_hit(case, quotes) if not r["abstained"] else (
                    None if case.get("out_of_scope") else False)
            except NotImplementedError:
                scoring_written = False
                d["evidence_hit"] = None
            time.sleep(sleep)  # stay under Groq's free 8,000 tokens/minute

    # 3) Report
    print(f"{'':4s}{'question':44s} {'top':>6s}  retr  evid  quote")
    for d in details:
        flag = lambda v: "-   " if v is None else ("yes " if v else "NO  ")
        print(f"{'OOS ' if d['out_of_scope'] else '    '}{d['question'][:44]:44s} {d['top_score']:6.3f}  "
              f"{flag(d['retrieval_hit'])}  {flag(d.get('evidence_hit'))}  "
              f"{d.get('grounding', '-') if not d.get('abstained') else 'abstained:' + d['abstained']}")

    ins = [d["top_score"] for d in details if not d["out_of_scope"]]
    oos = [d["top_score"] for d in details if d["out_of_scope"]]
    scores = {"retrieval_hit": pct([d["retrieval_hit"] for d in details])}
    if args.llm:
        answered = [d for d in details if not d.get("abstained")]
        scores.update(evidence_hit=pct([d.get("evidence_hit") for d in details]) if scoring_written else None,
                      abstain_ok=pct([d.get("abstain_ok") for d in details]),
                      grounded=pct([d.get("grounding") == "grounded" for d in answered]),
                      tokens=sum(d.get("tokens", 0) for d in details))
    print("\nScores (%):", json.dumps(scores, ensure_ascii=False))
    if args.llm and not scoring_written:
        print("evidence score: not implemented yet — write learning.evidence_matches (backend/app/learning.py)")
    if ins and oos:
        if min(ins) > max(oos):
            print(f"→ Suggested MIN_COSINE_SCORE ≈ {(min(ins) + max(oos)) / 2:.3f} "
                  f"(in-scope min {min(ins):.3f} > out-of-scope max {max(oos):.3f}). Current: {settings.min_cosine_score}")
        else:
            print(f"→ No clean gap (in-scope min {min(ins):.3f} ≤ out-of-scope max {max(oos):.3f}): keep "
                  f"MIN_COSINE_SCORE near {max(oos):.3f} and let the model's abstention handle the rest.")

    if args.save:
        s = engine.settings
        run = {"label": args.label or None, "scores": scores, "details": details, "settings": {
            "model": s.groq_model, "reasoning_effort": s.reasoning_effort, "min_cosine_score": s.min_cosine_score,
            "cosine_margin": s.cosine_margin, "max_k": s.max_k, "use_corrections": s.use_corrections,
            "prompt_md5": hashlib.md5(SYSTEM_PROMPT.encode()).hexdigest()[:10], "llm": args.llm}}
        saved = store.insert("eval_runs", run)
        print(f"Saved as eval run #{saved.get('id')}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
