"""FastAPI app. Run:  uvicorn app.main:app --reload --port 8000   (from the backend/ folder)"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .chunking import build_corpus
from .config import MADHAHIB, settings
from .rag import RagEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("nour.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests inject their own engine (fake models) before startup; otherwise build the real one.
    if getattr(app.state, "engine", None) is None:
        corpus = build_corpus(settings)
        if os.getenv("NOUR_FAKE_MODELS") == "1":  # demo mode: UI work without models / API key
            import chromadb
            from .dev_fakes import FakeEmbedder, FakeLLM, FakeReranker
            log.warning("DEMO MODE: fake models, answers are not real")
            app.state.demo = True
            engine = RagEngine(corpus, settings, FakeEmbedder(), FakeReranker(), FakeLLM(),
                               chroma_client=chromadb.EphemeralClient())
        else:
            engine = RagEngine(corpus, settings)
        log.info("Corpus: %d units, %d chunks — loading models and index…", len(corpus.units), len(corpus.chunks))
        log.info("Index %s", engine.ensure_index())
        app.state.engine = engine
    yield


app = FastAPI(title="Nour API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_methods=["*"], allow_headers=["*"])


def engine(request: Request) -> RagEngine:
    return request.app.state.engine


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    madhhab: str = "maliki"


@app.get("/api/health")
def health(request: Request):
    e = engine(request)
    return {"status": "ok", "units": len(e.corpus.units), "chunks": len(e.corpus.chunks),
            "index_ready": e.coll is not None, "llm": settings.groq_model,
            "demo": bool(getattr(request.app.state, "demo", False))}


@app.get("/api/madhahib")
def madhahib():
    return MADHAHIB


@app.get("/api/books")
def books(request: Request, madhhab: str = "maliki"):
    e = engine(request)
    return [{"key": b.key, "title": b.title, "author": b.author, "madhhab": b.madhhab,
             "babs": [{"index": bab["index"], "title": bab["title"], "units": len(bab["unit_keys"])}
                      for bab in b.babs]}
            for b in e.corpus.books.values() if b.madhhab == madhhab]


@app.get("/api/books/{book_key}/babs/{bab_index}")
def bab(request: Request, book_key: str, bab_index: int):
    e = engine(request)
    book = e.corpus.books.get(book_key)
    if book is None or not 0 <= bab_index < len(book.babs):
        raise HTTPException(404, "bab not found")
    b = book.babs[bab_index]
    units = [e.corpus.units[k] for k in b["unit_keys"]]
    return {
        "book_key": book.key, "book": book.title, "author": book.author,
        "bab_index": bab_index, "bab_title": b["title"],
        "prev": bab_index - 1 if bab_index > 0 else None,
        "next": bab_index + 1 if bab_index + 1 < len(book.babs) else None,
        "units": [{"key": u.key, "number": u.number, "section": u.section, "text": u.text} for u in units],
    }


@app.post("/api/ask")
def ask(request: Request, body: AskRequest):
    if not any(m["key"] == body.madhhab and m["available"] for m in MADHAHIB):
        raise HTTPException(400, "هذا المذهب غير متاح بعد")
    try:
        return engine(request).ask(body.question.strip(), body.madhhab)
    except RuntimeError as exc:  # e.g. missing GROQ_API_KEY
        raise HTTPException(503, str(exc)) from exc
