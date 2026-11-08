"""The HTTP clients, checked against fake transports (no network)."""
import dataclasses
import json

import httpx
import pytest

from app.chunking import corpus_from_units, unit_rows
from app.config import settings
from app.models import CloudflareEmbedder, GroqLLM
from app.store import SupabaseStore, vector_literal

S = dataclasses.replace(settings, supabase_url="https://x.supabase.co", supabase_key="sb_secret_abc",
                        cf_account_id="acc", cf_api_token="tok", groq_api_key="gk",
                        groq_model="openai/gpt-oss-120b")


def client(handler, **kw):
    return httpx.Client(transport=httpx.MockTransport(handler), **kw)


def test_store_match_and_paging():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.url.path.endswith("/rpc/match_chunks"):
            body = json.loads(req.content)
            assert body["query_embedding"].startswith("[0.5000000,") and body["filter_madhhab"] == "maliki"
            return httpx.Response(200, json=[{"id": "a", "similarity": 0.9}])
        if req.url.path.endswith("/units"):
            start = int(req.headers["Range"].split("-")[0])
            n = 1000 if start == 0 else 3  # two pages
            return httpx.Response(200, json=[{"key": f"k{start + i}"} for i in range(n)])
        return httpx.Response(404)

    st = SupabaseStore(S)
    st.http = client(handler, base_url="https://x.supabase.co/rest/v1", headers=st.http.headers)
    assert st.match([0.5, 0.25], "maliki", 5)[0]["id"] == "a"
    assert len(st.load_units()) == 1003
    assert seen[0].headers["apikey"] == "sb_secret_abc"
    assert "authorization" not in seen[0].headers  # new-style secret key: apikey header only


def test_store_legacy_jwt_key_sends_bearer():
    st = SupabaseStore(dataclasses.replace(S, supabase_key="eyJhbGciOi.fake"))
    assert st.http.headers["Authorization"] == "Bearer eyJhbGciOi.fake"


def test_store_delete_requires_filter():
    st = SupabaseStore(S)
    with pytest.raises(ValueError):
        st.delete_where("chunks")


def test_vector_literal():
    assert vector_literal([1, 0.5]) == "[1.0000000,0.5000000]"


def test_cloudflare_batches_and_normalizes():
    calls = []

    def handler(req):
        texts = json.loads(req.content)["text"]
        calls.append(len(texts))
        assert req.url.path == "/client/v4/accounts/acc/ai/run/@cf/baai/bge-m3"
        return httpx.Response(200, json={"success": True, "result": {
            "shape": [len(texts), 1024], "data": [[3.0, 4.0] + [0.0] * 1022 for _ in texts]}})

    emb = CloudflareEmbedder(S, client=client(handler))
    vecs = emb.encode(["t"] * 150)
    assert calls == [100, 50]  # API max batch = 100
    assert vecs[0][:2] == [0.6, 0.8]  # L2-normalized


def test_cloudflare_wrong_dim_is_an_error():
    emb = CloudflareEmbedder(S, client=client(lambda r: httpx.Response(
        200, json={"success": True, "result": {"shape": [1, 768], "data": [[0.1] * 768]}})))
    with pytest.raises(RuntimeError, match="shape"):
        emb.encode(["x"])


def test_groq_payload_and_retry(monkeypatch):
    monkeypatch.setattr("app.models.time.sleep", lambda s: None)
    n = {"calls": 0}

    def handler(req):
        n["calls"] += 1
        body = json.loads(req.content)
        assert body["model"] == "openai/gpt-oss-120b"
        assert body["reasoning_effort"] == "low" and body["include_reasoning"] is False
        if n["calls"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"choices": [{"message": {"content": " الجواب: نعم "}}],
                                         "usage": {"total_tokens": 42}})

    text, tokens = GroqLLM(S, client=client(handler)).complete([{"role": "user", "content": "x"}])
    assert (text, tokens, n["calls"]) == ("الجواب: نعم", 42, 2)


def test_groq_rate_limit_message(monkeypatch):
    monkeypatch.setattr("app.models.time.sleep", lambda s: None)
    llm = GroqLLM(S, client=client(lambda r: httpx.Response(429)))
    with pytest.raises(RuntimeError, match="تجاوز حد الطلبات"):
        llm.complete([{"role": "user", "content": "x"}])


def test_units_roundtrip(corpus):
    back = corpus_from_units(unit_rows(corpus))
    assert back.units.keys() == corpus.units.keys()
    k = "akhdari-05-001"
    assert back.units[k].text == corpus.units[k].text
    assert [b["title"] for b in back.books["risala"].babs] == [b["title"] for b in corpus.books["risala"].babs]
