"""The "learning" logic of Nour — YOUR part to write (Boch).

Three small functions. Everything around them (database, API, UI, evaluation, prompt
injection) is already wired. Until a function is written it raises NotImplementedError,
and the code that calls it degrades safely:
- evaluate.py prints "evidence score: not implemented yet";
- the site does not add corrections to the prompt (and USE_CORRECTIONS is off by default).

Check your work with:  cd backend && pytest -q tests/test_learning.py
(those tests are skipped while a function is not implemented, and run once it is.)

Helpers you may use (already in the project):
- app.chunking.normalize_ar(text): removes diacritics/tatweel, unifies alef forms, collapses spaces.
- app.chunking.find_quote_spans(text, quote): where `quote` appears in `text`, ignoring
  diacritics and punctuation; None if it does not appear.
"""
from __future__ import annotations


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

    Things to decide yourself: is a very short quote (2–3 words) enough? Does word order matter?
    """
    raise NotImplementedError


def pick_corrections(candidates: list[dict], min_similarity: float, max_examples: int) -> list[dict]:
    """Choose which past corrections to show the model as worked examples.

    candidates: rows from the Supabase `corrections` table, closest first, each like
        {"id": 3, "question": "...", "answer": "...", "evidence": ["...", ...],
         "similarity": 0.91}          # cosine similarity between the two questions (−1..1)
    min_similarity: from settings (CORRECTION_MIN_SIMILARITY, default 0.85)
    max_examples:   from settings (MAX_CORRECTION_EXAMPLES, default 2)

    Return the corrections to use (possibly an empty list), best first.

    Things to decide yourself: only keep near-duplicates of the new question? Avoid two
    corrections that say the same thing? What if the best one is just under the threshold?
    """
    raise NotImplementedError


def format_example(correction: dict) -> str:
    """Turn one correction into the text of a worked example inside the prompt.

    correction: one row returned by pick_corrections (see above).

    The model reads it before the passages, so it should show the METHOD: for a question
    like this one, this is the sentence that answers it, and this is the short answer.
    Keep it short (each example costs Groq tokens), and in the same format the model must
    answer in («الجواب: …» then «الدليل: «…»»), so the model copies the format too.
    The model is told to quote only from the numbered passages, never from the examples.
    """
    raise NotImplementedError
