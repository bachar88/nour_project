"""Text → babs → units → segments → chunks (same logic as the v2 notebook).

Vocabulary
- bab:     a chapter, detected from header lines starting with «باب».
- unit:    a block about one topic: a فصل / (وسننه) paragraph in Al-Akhdari, a whole bab in
           Al-Risala (whose blank lines are page breaks, re-joined here).
- segment: smallest piece — a sentence, or the text between two ruling markers («ومن», «وأما»…).
- chunk:   a few consecutive segments of one unit (~chunk_target_chars), overlapping by
           segment_overlap. Chunks are what gets embedded; units are what the reader shows.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .config import Settings, Source

TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
ALEFS = re.compile("[إأآٱ]")


def normalize_ar(text: str) -> str:
    """Remove diacritics/tatweel and unify alef forms (used for search, never for display)."""
    text = TASHKEEL.sub("", text).replace("ـ", "")
    text = ALEFS.sub("ا", text)
    return re.sub(r"\s+", " ", text).strip()


HEADER = re.compile(r"^[ \t]*\[?\s*(باب[^\]\n]{0,150})\]?[ \t]*$", re.MULTILINE)
END_PUNCT = tuple(".؟!:۔")
TITLE_LIKE = re.compile(r"^(?:\(|فصل|\S+(?:\s+\S+){0,3}\s*:)")
MARKERS = r"ومن|وأما|وإذا|وإن كان|ويستحب|ويكره|ويجوز|ولا يجوز|وكل|وقيل|واختلف|وكذلك|ووقت|وأول|والسنة"
SEG_SPLIT = re.compile(rf"(?<=[.؟!۔])\s+|\s+(?=(?:{MARKERS})\s)")


def split_into_babs(text: str) -> list[tuple[str, str]]:
    ms = list(HEADER.finditer(text))
    if not ms:
        return [("—", text)]
    babs = []
    if text[: ms[0].start()].strip():
        babs.append(("مقدمة", text[: ms[0].start()].strip()))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        babs.append((m.group(1).strip(" []"), text[m.end():end].strip()))
    return babs


def split_into_units(body: str) -> list[str]:
    """Blank lines are real paragraph breaks OR page breaks (mid-sentence): glue the latter back."""
    units: list[str] = []
    for p in re.split(r"\n\s*\n", body):
        p = re.sub(r"\s+", " ", p).strip()
        if not p:
            continue
        if units and not units[-1].endswith(END_PUNCT) and not TITLE_LIKE.match(p):
            units[-1] += " " + p
        else:
            units.append(p)
    return units


def unit_section(unit: str, current: str, bab_title: str) -> tuple[str, str]:
    """Return (label of this unit, label inherited by the following units)."""
    m = re.match(r"^\((\S[^)]{0,30})\)", unit)  # (وسننه) / (وفضائله)
    if m:
        return f"{current} — {m.group(1)}", current
    f = re.match(r"^فصل\s*:?\s*", unit)
    rest = unit[f.end():] if f else unit
    t = re.match(r"^([^:،.()]{2,40})\s*:", rest)  # «فرائض الوضوء سبع:»
    if f or t:
        title = t.group(1).strip() if t else " ".join(rest.split()[:6])
        return title, title
    return current or bab_title, current or bab_title


def split_into_segments(unit: str, max_chars: int) -> list[str]:
    segs = []
    for s in SEG_SPLIT.split(unit):
        s = s.strip()
        if not s:
            continue
        while len(s) > max_chars:  # no marker for too long → cut on a space
            cut = s.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            segs.append(s[:cut].strip())
            s = s[cut:].strip()
        if s:
            segs.append(s)
    return segs


def pack(segs: list[str], target: int, overlap: int) -> list[tuple[int, int]]:
    """Greedy packing into [start, end) segment ranges of ~target chars, stepping back `overlap`."""
    ranges, i = [], 0
    while i < len(segs):
        j, size = i, 0
        while j < len(segs) and (size == 0 or size + len(segs[j]) <= target):
            size += len(segs[j]) + 1
            j += 1
        ranges.append((i, j))
        if j >= len(segs):
            break
        i = max(j - overlap, i + 1)
    return ranges


@dataclass
class Unit:
    key: str
    book_key: str
    bab_index: int
    bab_title: str
    section: str
    number: int  # 1..N inside its book, shown in the reader like a hadith number
    segments: list[str]

    @property
    def text(self) -> str:
        return " ".join(self.segments)


@dataclass
class Chunk:
    id: str
    text: str
    embed_text: str
    metadata: dict


@dataclass
class Book:
    key: str
    title: str
    author: str
    madhhab: str
    babs: list[dict] = field(default_factory=list)  # {"index", "title", "unit_keys"}


@dataclass
class Corpus:
    books: dict[str, Book]
    units: dict[str, Unit]
    chunks: list[Chunk]
    fingerprint: str


def build_corpus(settings: Settings) -> Corpus:
    books: dict[str, Book] = {}
    units: dict[str, Unit] = {}
    chunks: list[Chunk] = []
    raw_texts = []

    for src in settings.sources:
        text = src.path.read_text(encoding="utf-8")
        raw_texts.append(text)
        book = Book(src.key, src.title, src.author, src.madhhab)
        books[src.key] = book
        number = 0
        for b, (bab_title, body) in enumerate(split_into_babs(text)):
            bab = {"index": b, "title": bab_title, "unit_keys": []}
            book.babs.append(bab)
            current = ""
            for u, unit_text in enumerate(split_into_units(body)):
                section, current = unit_section(unit_text, current, bab_title)
                segs = split_into_segments(unit_text, settings.max_segment_chars)
                if not segs:
                    continue
                number += 1
                key = f"{src.key}-{b:02d}-{u:03d}"
                units[key] = Unit(key, src.key, b, bab_title, section, number, segs)
                bab["unit_keys"].append(key)
                for k, (a, z) in enumerate(pack(segs, settings.chunk_target_chars, settings.segment_overlap)):
                    chunk_text = " ".join(segs[a:z])
                    if len(chunk_text) < settings.min_chunk_chars:
                        continue
                    chunks.append(Chunk(
                        id=f"{key}-{k:02d}",
                        text=chunk_text,
                        embed_text=normalize_ar(f"{bab_title} › {section}: {chunk_text}"),
                        metadata={
                            "book_key": src.key, "book": src.title, "author": src.author,
                            "madhhab": src.madhhab, "bab_index": b, "bab_title": bab_title,
                            "section": section, "unit_key": key, "seg_start": a, "seg_end": z,
                        },
                    ))

    fingerprint = hashlib.md5(("".join(raw_texts) + repr((
        settings.cf_embed_model, settings.chunk_target_chars, settings.max_segment_chars,
        settings.segment_overlap, settings.min_chunk_chars, MARKERS))).encode()).hexdigest()
    return Corpus(books, units, chunks, fingerprint)


def corpus_from_units(rows: list[dict]) -> Corpus:
    """Rebuild books/units from the Supabase `units` table (what the API serves in production)."""
    books: dict[str, Book] = {}
    units: dict[str, Unit] = {}
    for r in sorted(rows, key=lambda r: (r["book_key"], r["bab_index"], r["number"])):
        book = books.get(r["book_key"])
        if book is None:
            book = books[r["book_key"]] = Book(r["book_key"], r["book"], r["author"], r["madhhab"])
        while len(book.babs) <= r["bab_index"]:
            book.babs.append({"index": len(book.babs), "title": "", "unit_keys": []})
        bab = book.babs[r["bab_index"]]
        bab["title"] = r["bab_title"]
        bab["unit_keys"].append(r["key"])
        units[r["key"]] = Unit(r["key"], r["book_key"], r["bab_index"], r["bab_title"],
                               r["section"], r["number"], list(r["segments"]))
    # Bab indices stay as stored (units and links refer to them); a gap stays as an empty bab.
    return Corpus(books, units, [], "")


def unit_rows(corpus: Corpus) -> list[dict]:
    """Corpus → rows for the Supabase `units` table (inverse of corpus_from_units)."""
    rows = []
    for u in corpus.units.values():
        b = corpus.books[u.book_key]
        rows.append({"key": u.key, "book_key": u.book_key, "book": b.title, "author": b.author,
                     "madhhab": b.madhhab, "bab_index": u.bab_index, "bab_title": u.bab_title,
                     "section": u.section, "number": u.number, "segments": u.segments})
    return rows


# ---------- quote matching (grounding + highlight) ----------

def _word_index(text: str) -> tuple[str, list[int]]:
    """Normalized 'words only' string + for each of its chars, the index in the original text.
    Diacritics are dropped, alef forms unified, any run of non-word chars becomes one space."""
    out, pos = [], []
    pending_space = False
    for i, ch in enumerate(text):
        if TASHKEEL.match(ch) or ch == "ـ":
            continue
        if ALEFS.match(ch):
            ch = "ا"
        if ch.isalnum() or ch == "_":
            if pending_space and out:
                out.append(" ")
                pos.append(i)
            pending_space = False
            out.append(ch)
            pos.append(i)
        else:
            pending_space = True
    return "".join(out), pos


CONJUNCTIONS = ("و", "ف")


def conjunction_variants(norm_words: str):
    """The same words with the leading «و»/«ف» of the first word dropped or added.
    Models often quote «أما السنة…» for the book's «وأما السنة…» (or the reverse)."""
    yield norm_words
    first, _, rest = norm_words.partition(" ")
    tail = f" {rest}" if rest else ""
    if first[:1] in CONJUNCTIONS and len(first) > 2:
        yield first[1:] + tail
    else:
        for c in CONJUNCTIONS:
            yield c + first + tail


def find_quote_spans(text: str, quote: str) -> list[tuple[int, int]] | None:
    """Character spans of `quote` inside `text`, robust to diacritics, punctuation and a leading
    «و»/«ف» dropped or added. A quote elided with «...» / «…» is matched piece by piece.
    None if any piece is missing."""
    norm_text, pos = _word_index(text)
    padded = f" {norm_text} "
    spans = []
    for piece in re.split(r"\.\.\.|…", quote):
        norm_piece, _ = _word_index(piece)
        if not norm_piece:
            continue
        for variant in conjunction_variants(norm_piece):
            idx = padded.find(f" {variant} ")
            if idx >= 0:
                break
        else:
            return None
        start, end = idx, idx + len(variant) - 1  # indices in norm_text
        spans.append((pos[start], pos[end] + 1))
    return spans or None
