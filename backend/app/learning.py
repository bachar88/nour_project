"""The "learning" logic of Nour: three small functions, each with the choices it makes written
in its docstring. Everything around them (database, API, UI, evaluation, prompt injection) is
wired elsewhere. If one of them raises NotImplementedError, the callers degrade safely
(evaluate.py reports it; the site skips corrections).

Tests: cd backend && pytest -q tests/test_learning.py
Tuning knobs: the constants below, and on Vercel CORRECTION_MIN_SIMILARITY / MAX_CORRECTION_EXAMPLES.

Helpers you may use (already in the project):
- app.chunking.normalize_ar(text): removes diacritics/tatweel, unifies alef forms, collapses spaces.
- app.chunking.find_quote_spans(text, quote): where `quote` appears in `text`, ignoring
  diacritics and punctuation; None if it does not appear.
"""
from __future__ import annotations

import re

from .chunking import conjunction_variants, normalize_ar

MIN_WORDS = 3          # a quote or key shorter than this is too vague to count as evidence
MIN_COVERAGE = 0.6     # a quote shorter than the key must still contain ≥ 60% of the key's words, in order
MAX_FIELD_CHARS = 220  # longest answer / evidence sentence copied into a worked example


def _words(text: str) -> list[str]:
    """Normalized words: no diacritics, unified alef, no punctuation."""
    return re.sub(r"[^\w\s]", " ", normalize_ar(text)).split()


def _variants(words: list[str]) -> list[list[str]]:
    """The words as given, plus with a leading «و»/«ف» dropped or added on the first word
    (models often quote «أما السنة…» for the book's «وأما السنة…»)."""
    return [v.split() for v in conjunction_variants(" ".join(words))] if words else [words]


def _contains(longer: list[str], shorter: list[str]) -> bool:
    """True if `shorter` appears as consecutive words inside `longer`."""
    return f" {' '.join(shorter)} " in f" {' '.join(longer)} "


def _clip(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def evidence_matches(quote: str, expected: str) -> bool:
    """Is the sentence the model quoted the evidence we expected?

    Used by the evaluation (golden set) to score "right passage, wrong sentence" mistakes.

    quote:    what the model put between «» — e.g. «ومن نسي السجود القبلي حتى سلم سجد إن كان قريبا»
    expected: a sentence from the answer key — e.g. «فللنقصان سجدتان قبل السلام»

    Should return True when they are "the same evidence" even if:
    - one has diacritics / different alef forms / punctuation and the other not,
    - the model quoted a bit more or a bit less than the key (the key sentence is inside
      the quote, or the quote is inside the key sentence).
    Should return False for a different sentence that only shares some words
    (e.g. both contain «قبل السلام»).

    Choices made: under 3 words is too vague; word order matters (consecutive words);
    a quote that is part of the key must cover at least 60% of the key's words;
    a leading «و»/«ف» dropped or added on the first word is tolerated.
    """
    key = _words(expected)
    if len(key) < MIN_WORDS:
        return False
    # the model may elide with «...» / «…»: each piece is checked on its own
    for piece in re.split(r"\.\.\.|…", quote):
        q = _words(piece)
        if len(q) < MIN_WORDS:
            continue
        for k in _variants(key):
            if _contains(q, k):                                       # quoted the key (and maybe more)
                return True
        for qv in _variants(q):
            if _contains(key, qv) and len(qv) >= MIN_COVERAGE * len(key):  # quoted most of the key
                return True
    return False


def pick_corrections(candidates: list[dict], min_similarity: float, max_examples: int) -> list[dict]:
    """Choose which past corrections to show the model as worked examples.

    candidates: rows from the Supabase `corrections` table, closest first, each like
        {"id": 3, "question": "...", "answer": "...", "evidence": ["...", ...],
         "similarity": 0.91}          # cosine similarity between the two questions (−1..1)
    min_similarity: from settings (CORRECTION_MIN_SIMILARITY, default 0.85)
    max_examples:   from settings (MAX_CORRECTION_EXAMPLES, default 2)

    Return the corrections to use (possibly an empty list), best first.

    Choices made: strict threshold (a near miss is not shown: a wrong example is worse than none);
    two corrections citing the same evidence count once (keep the closest).
    """
    picked, seen = [], set()
    for c in sorted(candidates, key=lambda c: -c.get("similarity", -1.0)):
        if c.get("similarity", -1.0) < min_similarity:
            break                                   # sorted: everything after is farther
        evidence_key = tuple(sorted(" ".join(_words(e)) for e in c.get("evidence") or []))
        if not evidence_key or evidence_key in seen:
            continue                                # no evidence, or same lesson as a closer one
        seen.add(evidence_key)
        picked.append(c)
        if len(picked) >= max_examples:
            break
    return picked


def format_example(correction: dict) -> str:
    """Turn one correction into the text of a worked example inside the prompt.

    correction: one row returned by pick_corrections (see above).

    The model reads it before the passages, so it should show the METHOD: for a question
    like this one, this is the sentence that answers it, and this is the short answer.
    Keep it short (each example costs Groq tokens), and in the same format the model must
    answer in («الجواب: …» then «الدليل: «…»»), so the model copies the format too.
    The model is told to quote only from the numbered passages, never from the examples.
    """
    lines = [f"سؤال مشابه: {_clip(correction['question'])}",
             f"الجواب: {_clip(correction['answer'])}"]
    lines += [f"الدليل: «{_clip(e)}»" for e in correction.get("evidence") or []]
    return "\n".join(lines)
