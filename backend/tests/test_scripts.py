"""The indexing and evaluation scripts, against in-memory fakes."""
from app.dev_fakes import FakeEmbedder
from scripts import evaluate, index_supabase


class RecordingStore:
    def __init__(self):
        self.tables = {"units": {}, "chunks": {}, "index_meta": {}}
        self.log = []

    def get_meta(self, key):
        row = self.tables["index_meta"].get(key)
        return row["value"] if row else None

    def set_meta(self, key, value):
        self.upsert("index_meta", [{"key": key, "value": value}])

    def delete_where(self, table, **eq):
        self.log.append(("delete", table, eq))
        (k, v), = eq.items()
        gone = {key for key, r in self.tables[table].items() if r[k] == v}
        for key in gone:
            del self.tables[table][key]
        if table == "units":  # ON DELETE CASCADE
            self.tables["chunks"] = {i: c for i, c in self.tables["chunks"].items() if c["unit_key"] not in gone}

    def upsert(self, table, rows, batch=200):
        self.log.append(("upsert", table, len(rows)))
        pk = "key" if table in ("units", "index_meta") else "id"
        for r in rows:
            self.tables[table][r[pk]] = r


def test_index_then_skip_then_force(corpus):
    st = RecordingStore()
    assert index_supabase.main([], store=st, embedder=FakeEmbedder()) == 0
    assert len(st.tables["units"]) == len(corpus.units)
    assert len(st.tables["chunks"]) == len(corpus.chunks)
    assert st.tables["chunks"]["akhdari-05-001-00"]["embedding"].startswith("[")
    n = len(st.log)
    index_supabase.main([], store=st, embedder=FakeEmbedder())  # unchanged → skipped
    assert len(st.log) == n
    index_supabase.main(["--force", "--book", "akhdari"], store=st, embedder=FakeEmbedder())
    assert ("delete", "units", {"book_key": "akhdari"}) in st.log
    assert len(st.tables["chunks"]) == len(corpus.chunks)  # replaced, not duplicated


def test_unknown_book(corpus):
    assert index_supabase.main(["--book", "nope"], store=RecordingStore(), embedder=FakeEmbedder()) == 1


def test_evaluate_runs(make_engine, capsys):
    assert evaluate.main([], engine=make_engine()) == 0
    out = capsys.readouterr().out
    assert "Hit in context" in out and "OOS" in out
