"""Production wiring end to end — real SupabaseStore / CloudflareEmbedder / GroqLLM classes,
only the network is faked (Supabase REST, Cloudflare AI and Groq answered by one router)."""
import dataclasses
import json
import types

import httpx

from app import main
from app.chunking import unit_rows
from app.config import settings
from app.dev_fakes import DEMO_OVERRIDES, DIM, FakeEmbedder, FakeLLM, MemoryStore


def test_build_engine_and_ask(corpus, monkeypatch):
    fake_emb, fake_llm = FakeEmbedder(), FakeLLM()
    mem = MemoryStore(corpus, fake_emb)
    units = unit_rows(corpus)
    seen = []

    def router(req: httpx.Request):
        seen.append(f"{req.method} {req.url.host}{req.url.path}")
        if req.url.path.endswith("/rest/v1/units"):
            start, end = map(int, req.headers["Range"].split("-"))
            return httpx.Response(200, json=units[start:end + 1])
        if req.url.path.endswith("/rest/v1/rpc/match_chunks"):
            b = json.loads(req.content)
            vec = json.loads(b["query_embedding"])  # the vector literal must be valid JSON-like '[...]'
            return httpx.Response(200, json=mem.match(vec, b["filter_madhhab"], b["match_count"]))
        if req.url.host == "api.cloudflare.com":
            texts = json.loads(req.content)["text"]
            return httpx.Response(200, json={"success": True, "result": {
                "shape": [len(texts), DIM], "data": fake_emb.encode(texts)}})
        if req.url.host == "api.groq.com":
            text, tokens = fake_llm.complete(json.loads(req.content)["messages"])
            return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                                             "usage": {"total_tokens": tokens}})
        return httpx.Response(404)

    def client_factory(**kw):
        return httpx.Client(transport=httpx.MockTransport(router), **kw)

    fake_httpx = types.SimpleNamespace(Client=client_factory, Response=httpx.Response, URL=httpx.URL)
    monkeypatch.setattr("app.store.httpx", fake_httpx)
    monkeypatch.setattr("app.models.httpx", fake_httpx)
    s = dataclasses.replace(settings, supabase_url="https://p.supabase.co", supabase_key="sb_secret_x",
                            cf_account_id="a", cf_api_token="t", groq_api_key="g", embed_dim=DIM,
                            **DEMO_OVERRIDES)
    monkeypatch.setattr(main, "settings", s)
    monkeypatch.setattr(main, "DEMO", False)

    engine = main.build_engine()
    assert len(engine.corpus.units) == len(corpus.units)
    r = engine.ask("كم عدد سجدات القرآن إحدى عشرة سجدة")
    assert r["grounding"] == "grounded" and r["evidence"][0]["spans"]
    assert any("supabase.co/rest/v1/rpc/match_chunks" in x for x in seen)
    assert any(x.startswith("POST api.cloudflare.com") for x in seen)
    assert any(x.startswith("POST api.groq.com") for x in seen)
