"""Tests for YOUR functions in app/learning.py.
Each test is skipped while its function still raises NotImplementedError."""
import pytest

from app import learning


def call(fn, *args):
    try:
        return fn(*args)
    except NotImplementedError:
        pytest.skip(f"learning.{fn.__name__} is not implemented yet")


# ---------- evidence_matches ----------
KEY = "فللنقصان سجدتان قبل السلام"


def test_same_sentence():
    assert call(learning.evidence_matches, KEY, KEY) is True


def test_ignores_diacritics_and_punctuation():
    assert call(learning.evidence_matches, "فَلِلنُّقْصَانِ سَجْدَتَانِ، قَبْلَ السَّلَامِ.", KEY) is True


def test_quote_longer_than_key():
    quote = "وسجود السهو في الصلاة سنة، فللنقصان سجدتان قبل السلام بعد تمام التشهدين"
    assert call(learning.evidence_matches, quote, KEY) is True


def test_quote_a_bit_shorter_than_key():
    key = "ومن سافر مسافة أربعة برد وهي ثمانية وأربعون ميلا فعليه أن يقصر الصلاة"
    assert call(learning.evidence_matches, "ومن سافر مسافة أربعة برد وهي ثمانية وأربعون ميلا", key) is True


def test_wrong_sentence_sharing_words_is_rejected():
    # tonight's real mistake: same passage, shares «سجد … سلم … قبل», different ruling
    assert call(learning.evidence_matches, "ومن نسي السجود القبلي حتى سلم سجد إن كان قريبا", KEY) is False


def test_empty_quote_is_rejected():
    assert call(learning.evidence_matches, "", KEY) is False


# ---------- pick_corrections ----------
def rows(*sims):
    return [{"id": i, "question": f"q{i}", "answer": "a", "evidence": [f"جملة الدليل رقم {i}"], "similarity": s}
            for i, s in enumerate(sims)]


def test_threshold_and_limit():
    out = call(learning.pick_corrections, rows(0.95, 0.9, 0.88, 0.5), 0.85, 2)
    assert [r["id"] for r in out] == [0, 1]


def test_nothing_close_enough():
    assert call(learning.pick_corrections, rows(0.7, 0.6), 0.85, 2) == []


def test_same_evidence_counts_once():
    same = rows(0.95, 0.93, 0.9)
    same[1]["evidence"] = list(same[0]["evidence"])  # #1 teaches the same sentence as #0
    out = call(learning.pick_corrections, same, 0.85, 2)
    assert [r["id"] for r in out] == [0, 2]


def test_no_candidates():
    assert call(learning.pick_corrections, [], 0.85, 2) == []


# ---------- format_example ----------
def test_format_example_shows_method_and_format():
    c = {"id": 1, "question": "متى يكون سجود السهو قبل السلام؟", "answer": "يكون للنقصان.",
         "evidence": [KEY], "similarity": 0.93}
    text = call(learning.format_example, c)
    assert isinstance(text, str)
    assert c["question"] in text and KEY in text
    assert "الجواب" in text and "الدليل" in text
    assert len(text) < 600  # every example costs tokens


def test_dropped_conjunction_still_matches():
    assert call(learning.evidence_matches, "أما السنة الواحدة فلا سجود لها إلا السر والجهر",
                "وأما السنة الواحدة فلا سجود لها إلا السر والجهر") is True
