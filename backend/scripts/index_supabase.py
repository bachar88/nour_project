"""Chunk the books, embed the chunks with BGE-M3 (Cloudflare) and save everything into Supabase.

Run from backend/ (in the Colab admin notebook, or anywhere with the env variables set):
    python -m scripts.index_supabase            # skips if texts/settings are unchanged
    python -m scripts.index_supabase --force    # re-index anyway
    python -m scripts.index_supabase --book akhdari

For each book: all embeddings are computed first, then the book's old rows are replaced
(deleting a unit deletes its chunks), so the site only misses that book for a few seconds.
"""
from __future__ import annotations

import argparse
import sys
import time

from app.chunking import build_corpus, unit_rows
from app.config import settings
from app.models import CloudflareEmbedder
from app.store import SupabaseStore, vector_literal


def main(argv=None, store=None, embedder=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--force", action="store_true", help="re-index even if nothing changed")
    p.add_argument("--book", action="append", help="only this book key (repeatable)")
    args = p.parse_args(argv)

    missing = [m for m in settings.missing() if m != "GROQ_API_KEY"]  # Groq is not needed to index
    if missing and (store is None or embedder is None):
        print("Missing environment variables:", ", ".join(missing))
        return 1
    store = store or SupabaseStore(settings)
    embedder = embedder or CloudflareEmbedder(settings)

    corpus = build_corpus(settings)
    books = args.book or list(corpus.books)
    unknown = set(books) - set(corpus.books)
    if unknown:
        print("Unknown book key(s):", ", ".join(sorted(unknown)), "| known:", ", ".join(corpus.books))
        return 1

    if not args.force and not args.book and store.get_meta("fingerprint") == corpus.fingerprint:
        print("Index already up to date (same texts and settings). Use --force to rebuild.")
        return 0

    all_units = unit_rows(corpus)
    for key in books:
        t0 = time.time()
        units = [u for u in all_units if u["book_key"] == key]
        chunks = [c for c in corpus.chunks if c.metadata["book_key"] == key]
        print(f"[{key}] {len(units)} units, {len(chunks)} chunks → embedding…", flush=True)
        vecs = embedder.encode([c.embed_text for c in chunks])
        rows = [{"id": c.id, "unit_key": c.metadata["unit_key"], "madhhab": c.metadata["madhhab"],
                 "book_key": key, "seg_start": c.metadata["seg_start"], "seg_end": c.metadata["seg_end"],
                 "text": c.text, "embedding": vector_literal(v)} for c, v in zip(chunks, vecs)]
        store.delete_where("units", book_key=key)  # cascades to this book's chunks
        store.upsert("units", units)
        store.upsert("chunks", rows, batch=100)
        print(f"[{key}] done in {time.time() - t0:.1f}s", flush=True)

    if not args.book:
        store.set_meta("fingerprint", corpus.fingerprint)
    print("Index ready. Open /api/health?deep=1 on the site to check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
