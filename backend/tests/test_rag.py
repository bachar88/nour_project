from fastapi.testclient import TestClient


def test_retrieval_finds_right_text(make_engine):
    e = make_engine()
    r = e.retrieve("ما هي مسافة قصر الصلاة للمسافر أربعة برد", "maliki")
    assert r["passages"], "nothing selected"
    assert "أربعة برد" in r["passages"][0]["text"]
    assert len(r["passages"]) <= e.settings.max_k


def test_madhhab_filter(make_engine):
    assert make_engine().retrieve("مسافة قصر الصلاة", "hanafi")["candidates"] == []


def test_merge_removes_overlap(make_engine):
    e = make_engine()
    unit_chunks = [c for c in e.corpus.chunks if c.metadata["unit_key"] == "akhdari-06-000"][:2]
    hits = [{"text": c.text, "metadata": c.metadata, "score": s} for c, s in zip(unit_chunks, (0.9, 0.8))]
    merged = e.merge_hits(hits)
    assert len(merged) == 1
    assert len(merged[0]["text"]) < sum(len(c.text) for c in unit_chunks)  # shared segment kept once


def test_ask_grounded_answer_has_spans(make_engine):
    e = make_engine("quote")
    r = e.ask("كم عدد سجدات القرآن إحدى عشرة سجدة")
    assert r["grounding"] == "grounded" and r["abstained"] is None
    ev = r["evidence"][0]
    unit_text = e.corpus.units[ev["unit_key"]].text
    s, t = ev["spans"][0]
    assert ev["quote"].split()[0] in unit_text[s:t]


def test_ask_flags_invented_quote(make_engine):
    r = make_engine("invent").ask("كم عدد سجدات القرآن إحدى عشرة سجدة")
    assert r["grounding"] == "not_found"
    assert r["evidence"][0]["found"] is False


def test_gate_skips_llm_for_unrelated_question(make_engine):
    e = make_engine()
    r = e.ask("qwerty zxcv")
    assert r["abstained"] == "retrieval" and e.llm.calls == 0


def test_model_abstention(make_engine):
    r = make_engine("abstain").ask("ما حكم الأذان والأذان واجب")
    assert r["abstained"] == "model" and r["evidence"] == []


def test_api(make_engine):
    from app.main import app
    app.state.engine = make_engine()
    try:
        c = TestClient(app)
        assert c.get("/api/health?deep=1").json()["db"] == "ok"
        books = c.get("/api/books").json()
        assert {b["key"] for b in books} == {"risala", "akhdari"}
        bab = c.get("/api/books/akhdari/babs/6").json()
        assert bab["bab_title"] == "باب في السهو" and bab["next"] is None and bab["units"]
        assert c.get("/api/books/akhdari/babs/99").status_code == 404
        r = c.post("/api/ask", json={"question": "كم عدد سجدات القرآن", "madhhab": "maliki"})
        assert r.status_code == 200 and r.json()["passages"]
        assert c.post("/api/ask", json={"question": "سؤال", "madhhab": "hanafi"}).status_code == 400
    finally:
        app.state.engine = None
