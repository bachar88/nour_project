"""The learning-loop plumbing: feedback API, corrections in the prompt, golden-set evaluation, review.
Your functions in app/learning.py are replaced here by tiny stand-ins, so these tests run either way."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import learning
from app.chunking import build_corpus, find_quote_spans
from app.config import settings
from app.dev_fakes import FakeEmbedder
from scripts import evaluate, review_feedback

KEY = "فللنقصان سجدتان قبل السلام"


class TableStore:
    """In-memory store with the PostgREST-like filters the scripts use (eq. only)."""
    def __init__(self, base=None):
        self.base, self.tables = base, {}

    def __getattr__(self, name):  # match(), ping()… come from the wrapped MemoryStore
        return getattr(self.base, name)

    def insert(self, table, row):
        rows = self.tables.setdefault(table, [])
        row = dict(row, id=len(rows) + 1, status=row.get("status", "new"), created_at="2026-11-08T23:00:00")
        rows.append(row)
        return row

    def select(self, table, **params):
        rows = self.tables.get(table, [])
        for k, v in params.items():
            if k not in ("order", "select") and str(v).startswith("eq."):
                rows = [r for r in rows if str(r.get(k)) == v[3:]]
        return rows

    def update(self, table, values, **eq):
        for r in self.select(table, **{k: f"eq.{v}" for k, v in eq.items()}):
            r.update(values)

    def match_corrections(self, embedding, madhhab, count):
        rows = [dict(r, similarity=0.95) for r in self.tables.get("corrections", []) if r["madhhab"] == madhhab]
        return rows[:count]


@pytest.fixture
def fake_learning(monkeypatch):
    monkeypatch.setattr(learning, "evidence_matches", lambda q, e: e in q or q in e)
    monkeypatch.setattr(learning, "pick_corrections", lambda rows, m, k: [r for r in rows if r["similarity"] >= m][:k])
    monkeypatch.setattr(learning, "format_example",
                        lambda c: f"سؤال: {c['question']}\nالجواب: {c['answer']}\nالدليل: «{c['evidence'][0]}»")


def test_golden_sentences_exist_in_books():
    corpus = build_corpus(settings)
    texts = [u.text for u in corpus.units.values()]
    for case in evaluate.load_golden():
        if case.get("out_of_scope"):
            continue
        for group in evaluate.groups(case):
            for e in group:
                assert any(find_quote_spans(t, e) for t in texts), e


def test_grouped_evidence_needs_every_group(fake_learning):
    case = {"question": "q", "expected_groups": [["سنن الصلاة: الإقامة، والسورة التي بعد الفاتحة"],
                                                 ["ولا يكون السجود القبلي إلا لترك سنتين فأكثر", "وأما السنة الواحدة فلا سجود لها"]]}
    rule_only = ["ولا يكون السجود القبلي إلا لترك سنتين فأكثر"]
    assert evaluate.evidence_hit(case, rule_only) is False
    assert evaluate.evidence_hit(case, rule_only + ["سنن الصلاة: الإقامة، والسورة التي بعد الفاتحة"]) is True


def test_feedback_endpoint(make_engine):
    from app.main import app
    e = make_engine()
    e.store = TableStore(e.store)
    app.state.engine = e
    try:
        c = TestClient(app)
        ok = c.post("/api/feedback", json={"question": "متى يكون سجود السهو قبل السلام؟", "rating": -1,
                                           "comment": "اختار جملة خاطئة", "correct_unit_key": "akhdari-06-000",
                                           "correct_quote": KEY})
        assert ok.status_code == 200 and ok.json()["id"] == 1
        assert e.store.tables["feedback"][0]["correct_quote"] == KEY
        bad = c.post("/api/feedback", json={"question": "سؤال", "rating": -1,
                                            "correct_unit_key": "akhdari-06-000", "correct_quote": "جملة مختلقة تماما"})
        assert bad.status_code == 422  # picked sentence must really be in that unit
        assert c.post("/api/feedback", json={"question": "سؤال", "rating": 5}).status_code == 422
        assert c.post("/api/feedback", json={"question": "سؤال", "rating": 1}).status_code == 200
    finally:
        app.state.engine = None


def test_corrections_reach_the_prompt(make_engine, fake_learning):
    e = make_engine()
    e.settings = dataclasses.replace(e.settings, use_corrections=True)
    e.store = TableStore(e.store)
    e.store.insert("corrections", {"madhhab": "maliki", "question": "متى السجود القبلي؟", "answer": "للنقصان.",
                                   "evidence": [KEY]})
    sent = {}
    real = e.llm.complete
    e.llm.complete = lambda msgs: (sent.setdefault("msgs", msgs), real(msgs))[1]
    r = e.ask("متى يكون سجود السهو قبل السلام؟ فللنقصان سجدتان")
    user = sent["msgs"][-1]["content"]
    assert "أمثلة محلولة" in user and "متى السجود القبلي؟" in user
    assert user.index("أمثلة محلولة") < user.index("المقاطع:")
    assert r["corrections_used"] == [1]


def test_corrections_off_or_unwritten_change_nothing(make_engine, monkeypatch):
    def not_written(*args):
        raise NotImplementedError
    monkeypatch.setattr(learning, "pick_corrections", not_written)  # as if learning.py were empty
    e = make_engine()
    e.store = TableStore(e.store)
    e.store.insert("corrections", {"madhhab": "maliki", "question": "x", "answer": "y", "evidence": [KEY]})
    assert e.ask("كم عدد سجدات القرآن")["corrections_used"] == []          # USE_CORRECTIONS off
    e.settings = dataclasses.replace(e.settings, use_corrections=True)
    assert e.ask("كم عدد سجدات القرآن")["corrections_used"] == []          # learning.py not written yet
    assert e.ask("كم عدد سجدات القرآن")["grounding"] == "grounded"


def test_evaluate_with_answers_and_save(make_engine, fake_learning, capsys):
    e = make_engine()
    store = TableStore(e.store)
    assert evaluate.main(["--llm", "--save", "--label", "t"], engine=e, store=store, sleep=0) == 0
    run = store.tables["eval_runs"][0]
    assert run["label"] == "t" and run["scores"]["retrieval_hit"] is not None
    assert run["scores"]["evidence_hit"] is not None and run["settings"]["prompt_md5"]
    assert len(run["details"]) == len(evaluate.load_golden())
    assert "Scores (%)" in capsys.readouterr().out


def test_evaluate_reports_unwritten_scoring(make_engine, capsys, monkeypatch):
    def not_written(*args):
        raise NotImplementedError
    monkeypatch.setattr(learning, "evidence_matches", not_written)
    assert evaluate.main(["--llm"], engine=make_engine(), sleep=0) == 0
    assert "not implemented yet" in capsys.readouterr().out


def test_review_accept_and_reject(make_engine, capsys):
    store = TableStore()
    store.insert("feedback", {"question": "متى يكون سجود السهو قبل السلام؟", "madhhab": "maliki", "rating": -1,
                              "correct_quote": KEY, "correct_unit_key": "akhdari-06-000"})
    store.insert("feedback", {"question": "سؤال", "madhhab": "maliki", "rating": -1})
    review_feedback.main(["list"], store=store)
    review_feedback.main(["accept", "1", "--answer", "للنقصان."], store=store, embedder=FakeEmbedder())
    review_feedback.main(["reject", "2"], store=store)
    out = capsys.readouterr().out
    assert "#1" in out and '"expected_evidence": ["' + KEY in out
    corr = store.tables["corrections"][0]
    assert corr["evidence"] == [KEY] and corr["embedding"].startswith("[") and corr["feedback_id"] == 1
    assert [f["status"] for f in store.tables["feedback"]] == ["accepted", "rejected"]
