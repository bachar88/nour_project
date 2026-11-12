"""Review what users reported, and turn good reports into corrections (worked examples).

    python -m scripts.review_feedback list                 # new reports, newest first
    python -m scripts.review_feedback list --all           # every report
    python -m scripts.review_feedback accept 12 --answer "يكون سجود السهو قبل السلام للنقصان."
    python -m scripts.review_feedback accept 12 --answer "…" --evidence "فللنقصان سجدتان قبل السلام"
    python -m scripts.review_feedback reject 12

accept: the evidence defaults to the sentence the user picked in the reader. The question is
embedded with BGE-M3 (same as at question time) and saved in `corrections`; the report becomes
'accepted'. It also prints the line to add to eval/golden.jsonl, so the mistake becomes a test.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.chunking import normalize_ar
from app.config import settings


def _store():
    from app.store import SupabaseStore
    return SupabaseStore(settings)


def _embedder():
    from app.models import CloudflareEmbedder
    return CloudflareEmbedder(settings)


def list_reports(store, show_all=False) -> list[dict]:
    params = {"order": "created_at.desc"}
    if not show_all:
        params["status"] = "eq.new"
    rows = store.select("feedback", **params)
    if not rows:
        print("No reports." if show_all else "No new reports.")
    for r in rows:
        print(f"#{r['id']}  {'👍' if r['rating'] == 1 else '👎'}  [{r['status']}]  {r['created_at'][:16]}")
        print(f"   Q: {r['question']}")
        if r.get("answer"):
            print(f"   A: {r['answer'][:200]}")
        if r.get("correct_quote"):
            print(f"   ✓ picked: «{r['correct_quote']}»  ({r.get('correct_unit_key')})")
        if r.get("comment"):
            print(f"   💬 {r['comment']}")
    return rows


def accept(store, embedder, report_id: int, answer: str, evidence: list[str] | None = None) -> dict:
    rows = store.select("feedback", id=f"eq.{report_id}")
    if not rows:
        raise SystemExit(f"Report #{report_id} not found")
    fb = rows[0]
    evidence = evidence or ([fb["correct_quote"]] if fb.get("correct_quote") else [])
    if not evidence:
        raise SystemExit("No evidence: the user did not pick a sentence, pass --evidence \"…\"")
    vec = embedder.encode([normalize_ar(fb["question"])])[0]
    from app.store import vector_literal
    row = store.insert("corrections", {
        "madhhab": fb["madhhab"], "question": fb["question"], "answer": answer,
        "evidence": evidence, "embedding": vector_literal(vec), "feedback_id": fb["id"]})
    store.update("feedback", {"status": "accepted"}, id=fb["id"])
    print(f"Correction #{row.get('id')} saved; report #{fb['id']} accepted.")
    print("Add this line to backend/eval/golden.jsonl so it becomes a test:")
    print(json.dumps({"question": fb["question"], "madhhab": fb["madhhab"], "expected_evidence": evidence},
                     ensure_ascii=False))
    return row


def reject(store, report_id: int) -> None:
    store.update("feedback", {"status": "rejected"}, id=report_id)
    print(f"Report #{report_id} rejected.")


def main(argv=None, store=None, embedder=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list"); l.add_argument("--all", action="store_true")
    a = sub.add_parser("accept"); a.add_argument("id", type=int); a.add_argument("--answer", required=True)
    a.add_argument("--evidence", action="append", help="correct sentence (repeatable)")
    r = sub.add_parser("reject"); r.add_argument("id", type=int)
    args = p.parse_args(argv)

    store = store or _store()
    if args.cmd == "list":
        list_reports(store, args.all)
    elif args.cmd == "accept":
        accept(store, embedder or _embedder(), args.id, args.answer, args.evidence)
    else:
        reject(store, args.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
