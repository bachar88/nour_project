"""FastAPI app.
- Vercel: served by api/index.py (see vercel.json).
- Local:  uvicorn app.main:app --port 8000          (from backend/, needs the .env keys)
- Demo:   NOUR_DEMO=1 uvicorn app.main:app --port 8000   (no keys, fake models, answers not real)
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .chunking import find_quote_spans
from .config import MADHAHIB, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("nour.api")

app = FastAPI(title="Nour API")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_methods=["*"], allow_headers=["*"])

_lock = threading.Lock()
DEMO = os.getenv("NOUR_DEMO") == "1" or os.getenv("NOUR_FAKE_MODELS") == "1"


def build_engine():
    """Created on the first request and kept while the serverless instance stays warm."""
    if DEMO:
        from .dev_fakes import demo_engine
        log.warning("DEMO MODE: fake models, answers are not real")
        return demo_engine(settings)
    missing = settings.missing()
    if missing:
        raise HTTPException(503, f"Missing environment variables: {', '.join(missing)}")
    from .chunking import corpus_from_units
    from .models import CloudflareEmbedder, GroqLLM
    from .rag import RagEngine
    from .store import SupabaseStore
    store = SupabaseStore(settings)
    corpus = corpus_from_units(store.load_units())
    if not corpus.units:
        raise HTTPException(503, "The database is empty: run the indexing notebook first.")
    log.info("Loaded %d units from Supabase", len(corpus.units))
    return RagEngine(corpus, settings, CloudflareEmbedder(settings), store, GroqLLM(settings))


def engine(request: Request):
    e = getattr(request.app.state, "engine", None)
    if e is None:
        with _lock:
            e = getattr(request.app.state, "engine", None)
            if e is None:
                e = request.app.state.engine = build_engine()
    return e


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    madhhab: str = "maliki"


class FeedbackRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    madhhab: str = "maliki"
    rating: Literal[-1, 1]                                   # -1 = 👎, 1 = 👍
    comment: str | None = Field(None, max_length=1000)
    correct_unit_key: str | None = Field(None, max_length=40)
    correct_quote: str | None = Field(None, min_length=3, max_length=800)
    answer: str | None = Field(None, max_length=2000)        # what the user saw (for review)
    evidence: list[dict] | None = Field(None, max_length=6)
    passages: list[dict] | None = Field(None, max_length=6)


@app.get("/api/health")
def health(request: Request, deep: bool = False):
    """deep=1 also queries the database (used by the keep-alive job so Supabase never pauses)."""
    info = {"status": "ok", "demo": DEMO, "llm": settings.groq_model}
    if deep:
        e = engine(request)  # raises 503 with the missing variables if not configured
        e.store.ping()
        info.update(units=len(e.corpus.units), db="ok")
    elif not DEMO and settings.missing():
        info.update(status="misconfigured", missing=settings.missing())
    return info


@app.get("/api/madhahib")
def madhahib():
    return MADHAHIB


@app.get("/api/books")
def books(request: Request, madhhab: str = "maliki"):
    e = engine(request)
    return [{"key": b.key, "title": b.title, "author": b.author, "madhhab": b.madhhab,
             "babs": [{"index": bab["index"], "title": bab["title"], "units": len(bab["unit_keys"])}
                      for bab in b.babs if bab["unit_keys"]]}
            for b in e.corpus.books.values() if b.madhhab == madhhab]


@app.get("/api/books/{book_key}/babs/{bab_index}")
def bab(request: Request, book_key: str, bab_index: int):
    e = engine(request)
    book = e.corpus.books.get(book_key)
    if book is None or not 0 <= bab_index < len(book.babs) or not book.babs[bab_index]["unit_keys"]:
        raise HTTPException(404, "bab not found")
    filled = [b["index"] for b in book.babs if b["unit_keys"]]
    pos = filled.index(bab_index)
    b = book.babs[bab_index]
    units = [e.corpus.units[k] for k in b["unit_keys"]]
    return {
        "book_key": book.key, "book": book.title, "author": book.author,
        "bab_index": bab_index, "bab_title": b["title"],
        "prev": filled[pos - 1] if pos > 0 else None,
        "next": filled[pos + 1] if pos + 1 < len(filled) else None,
        "units": [{"key": u.key, "number": u.number, "section": u.section, "text": u.text} for u in units],
    }


@app.post("/api/ask")
def ask(request: Request, body: AskRequest):
    if not any(m["key"] == body.madhhab and m["available"] for m in MADHAHIB):
        raise HTTPException(400, "هذا المذهب غير متاح بعد")
    try:
        return engine(request).ask(body.question.strip(), body.madhhab)
    except RuntimeError as exc:  # upstream service error (rate limit, bad key, ...)
        log.exception("ask failed")
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/feedback")
def feedback(request: Request, body: FeedbackRequest):
    """Store a 👍 / 👎 (and optionally the correct sentence picked in the reader) for later review
    in the admin notebook. Nothing changes in the answers until a reviewer accepts it."""
    e = engine(request)
    if (body.correct_quote is None) != (body.correct_unit_key is None):
        raise HTTPException(422, "correct_quote and correct_unit_key go together")
    if body.correct_unit_key is not None:
        unit = e.corpus.units.get(body.correct_unit_key)
        if unit is None or not find_quote_spans(unit.text, body.correct_quote):
            raise HTTPException(422, "the picked sentence is not in that unit")
    try:
        row = e.store.insert("feedback", body.model_dump())
    except RuntimeError as exc:
        log.exception("feedback insert failed")
        raise HTTPException(503, "تعذّر حفظ الملاحظة، أعد المحاولة لاحقًا.") from exc
    return {"id": row.get("id"), "status": "saved"}
