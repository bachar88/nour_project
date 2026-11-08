"""Export the chunked corpus to JSON for the browser-only preview build (frontend/src/preview).
Run from backend/:  python -m scripts.export_corpus"""
import json
from pathlib import Path

from app.chunking import build_corpus
from app.config import settings

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "preview" / "corpus.json"

corpus = build_corpus(settings)
data = {
    "books": [{"key": b.key, "title": b.title, "author": b.author, "madhhab": b.madhhab,
               "babs": [{"index": x["index"], "title": x["title"], "unit_keys": x["unit_keys"]} for x in b.babs]}
              for b in corpus.books.values()],
    "units": {k: {"book_key": u.book_key, "bab_index": u.bab_index, "bab_title": u.bab_title,
                  "section": u.section, "number": u.number, "segments": u.segments}
              for k, u in corpus.units.items()},
    "chunks": [{"id": c.id, "unit_key": c.metadata["unit_key"], "seg_start": c.metadata["seg_start"],
                "seg_end": c.metadata["seg_end"]} for c in corpus.chunks],
}
OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(data['chunks'])} chunks)")
