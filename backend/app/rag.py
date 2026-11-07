"""Retrieve → rerank → adaptive selection → merge → generate → check the quotes."""
from __future__ import annotations

import logging
import re
import time

from .chunking import Corpus, find_quote_spans, normalize_ar
from .config import Settings

log = logging.getLogger("nour.rag")

ABSTAIN_TEXT = "لم يرد في النص ما يجيب عن هذا السؤال."

SYSTEM_PROMPT = f"""أنت مساعد يستخرج الأحكام من نصوص فقهية من المذهب المالكي، ولست مفتيًا.
القواعد:
1. اعتمد فقط على المقاطع المرقّمة المعطاة، ولا تستعمل أي معلومة من خارجها.
2. أجب عن السؤال المحدد فقط، وتجاهل باقي المسائل الموجودة في المقاطع.
3. لا تُضف حكمًا أو وصفًا (واجب، سنة، فضيلة، مكروه...) إلا إذا ورد حرفيًا في النص.
4. انقل الدليل من المقطع حرفيًا بين «» دون تغيير أي كلمة، ثم اذكر رقم المقطع بين معقوفين.
5. إن ذكر الكتابان المسألة بعبارتين مختلفتين فاذكر عبارة كل كتاب مع رقمه.
6. إن لم تُجب المقاطع عن السؤال صراحة، اكتب هذه الجملة فقط: {ABSTAIN_TEXT}

صيغة الإجابة:
الجواب: جملة أو جملتان.
الدليل: «نص منقول حرفيًا» [رقم المقطع]"""

QUOTE_RE = re.compile(r"«([^»]+)»\s*(?:\[(\d+)\])?")
ANSWER_RE = re.compile(r"الجواب\s*:\s*(.*?)(?=\n\s*الدليل\s*:|$)", re.S)


class RagEngine:
    def __init__(self, corpus: Corpus, settings: Settings, embedder=None, reranker=None, llm=None,
                 chroma_client=None):
        self.corpus = corpus
        self.settings = settings
        self._embedder, self._reranker, self._llm = embedder, reranker, llm
        self._chroma_client = chroma_client
        self.coll = None

    # ---------- lazy model loading ----------
    @property
    def embedder(self):
        if self._embedder is None:
            from .models import SentenceTransformerEmbedder
            log.info("Loading embedder %s", self.settings.embed_model)
            self._embedder = SentenceTransformerEmbedder(self.settings)
        return self._embedder

    @property
    def reranker(self):
        if self._reranker is None and self.settings.use_reranker:
            from .models import CrossEncoderReranker
            log.info("Loading reranker %s", self.settings.rerank_model)
            self._reranker = CrossEncoderReranker(self.settings)
        return self._reranker

    @property
    def llm(self):
        if self._llm is None:
            from .models import GroqLLM
            self._llm = GroqLLM(self.settings)
        return self._llm

    # ---------- index ----------
    def ensure_index(self) -> str:
        """Reuse the Chroma collection if texts/settings are unchanged, otherwise rebuild it."""
        import chromadb
        client = self._chroma_client or chromadb.PersistentClient(path=str(self.settings.chroma_dir))
        name = self.settings.collection
        try:
            coll = client.get_collection(name)
            if (coll.metadata or {}).get("fingerprint") != self.corpus.fingerprint:
                client.delete_collection(name)
                coll = None
        except Exception:
            coll = None
        if coll is not None:
            self.coll = coll
            return "reused"
        t0 = time.time()
        coll = client.create_collection(
            name, metadata={"hnsw:space": "cosine", "fingerprint": self.corpus.fingerprint})
        chunks = self.corpus.chunks
        vecs = self.embedder.encode([c.embed_text for c in chunks])
        for i in range(0, len(chunks), 500):
            part = chunks[i:i + 500]
            coll.add(ids=[c.id for c in part], documents=[c.text for c in part],
                     metadatas=[c.metadata for c in part],
                     embeddings=[list(map(float, v)) for v in vecs[i:i + 500]])
        self.coll = coll
        log.info("Indexed %d chunks in %.1fs", len(chunks), time.time() - t0)
        return "built"

    # ---------- retrieval ----------
    def retrieve(self, query: str, madhhab: str) -> dict:
        if self.coll is None:
            self.ensure_index()
        q_vec = self.embedder.encode([normalize_ar(query)])[0]
        res = self.coll.query(query_embeddings=[list(map(float, q_vec))],
                              n_results=min(self.settings.fetch_k, self.coll.count()),
                              where={"madhhab": madhhab},
                              include=["documents", "metadatas", "distances"])
        cands = [{"text": d, "metadata": m, "vec_score": 1 - dist, "score": 1 - dist}
                 for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]
        if self.reranker is not None and cands:
            for c, s in zip(cands, self.reranker.score(query, [c["text"] for c in cands])):
                c["score"] = s
            cands.sort(key=lambda c: -c["score"])
        return {"candidates": cands, "passages": self.select_context(cands)}

    def select_context(self, cands: list[dict]) -> list[dict]:
        """Keep only chunks close to the best one (max_k), merge, and respect a size budget.
        A fixed large TOP_K feeds the 7B model near-miss rulings, which it then mixes in."""
        if not cands:
            return []
        s, top = self.settings, cands[0]["score"]
        if self.reranker is not None:
            thr = max(s.min_rerank_score, s.rel_cutoff * top)
        else:
            thr = max(s.min_cosine_score, top - s.cosine_margin)
        kept = [c for c in cands if c["score"] >= thr][:s.max_k]
        out, total = [], 0
        for p in self.merge_hits(kept):
            if out and total + len(p["text"]) > s.max_context_chars:
                break
            out.append(p)
            total += len(p["text"])
        return out

    def merge_hits(self, hits: list[dict]) -> list[dict]:
        """Chunks from the same unit → one passage: each segment once, in reading order."""
        groups: dict[str, dict] = {}
        for h in hits:
            m = h["metadata"]
            g = groups.setdefault(m["unit_key"], {"metadata": m, "score": h["score"], "idx": set()})
            g["score"] = max(g["score"], h["score"])
            g["idx"].update(range(m["seg_start"], m["seg_end"]))
        passages = []
        for key, g in groups.items():
            segs = self.corpus.units[key].segments
            runs: list[list[int]] = []
            for i in sorted(g["idx"]):
                if runs and i == runs[-1][-1] + 1:
                    runs[-1].append(i)
                else:
                    runs.append([i])
            text = " … ".join(" ".join(segs[i] for i in r) for r in runs)
            passages.append({"text": text, "metadata": g["metadata"], "score": g["score"]})
        return sorted(passages, key=lambda p: -p["score"])

    # ---------- generation ----------
    @staticmethod
    def build_messages(query: str, passages: list[dict]) -> list[dict]:
        ctx = "\n\n".join(
            f"[{i}] ({p['metadata']['book']} — {p['metadata']['bab_title']})\n{p['text']}"
            for i, p in enumerate(passages, 1))
        return [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"المقاطع:\n{ctx}\n\nالسؤال: {query}"}]

    def parse_answer(self, raw: str, passages: list[dict]) -> tuple[str, list[dict], str]:
        """→ (short answer, evidence list, grounding status)."""
        m = ANSWER_RE.search(raw)
        answer = (m.group(1) if m else QUOTE_RE.split(raw)[0]).strip() or raw.strip()
        evidence, statuses = [], []
        for quote, num in QUOTE_RE.findall(raw):
            order = list(range(len(passages)))
            if num and 1 <= int(num) <= len(passages):
                order.remove(int(num) - 1)
                order.insert(0, int(num) - 1)
            found = None
            for i in order:  # the cited passage first, then the others
                if find_quote_spans(passages[i]["text"], quote):
                    found = i
                    break
            ev = {"quote": quote.strip(), "passage": (found + 1) if found is not None else (int(num) if num else None),
                  "found": found is not None, "unit_key": None, "spans": []}
            if found is not None:
                key = passages[found]["metadata"]["unit_key"]
                ev["unit_key"] = key
                ev["spans"] = find_quote_spans(self.corpus.units[key].text, quote) or []
            evidence.append(ev)
            statuses.append(ev["found"])
        if not evidence:
            grounding = "no_quote"
        else:
            grounding = "grounded" if all(statuses) else "not_found"
        return answer, evidence, grounding

    def ask(self, question: str, madhhab: str = "maliki") -> dict:
        t0 = time.time()
        r = self.retrieve(question, madhhab)
        passages = r["passages"]
        result = {"question": question, "madhhab": madhhab, "answer": ABSTAIN_TEXT, "raw": "",
                  "evidence": [], "grounding": "n/a", "abstained": None,
                  "passages": [self._public_passage(p) for p in passages], "tokens": 0}
        if not passages:  # score gate: nothing relevant enough → no LLM call
            result["abstained"] = "retrieval"
        else:
            raw, tokens = self.llm.complete(self.build_messages(question, passages))
            result.update(raw=raw, tokens=tokens)
            if normalize_ar(ABSTAIN_TEXT[:20]) in normalize_ar(raw):
                result["abstained"] = "model"
            else:
                result["answer"], result["evidence"], result["grounding"] = self.parse_answer(raw, passages)
        result["elapsed"] = round(time.time() - t0, 3)
        return result

    def _public_passage(self, p: dict) -> dict:
        m = p["metadata"]
        unit = self.corpus.units[m["unit_key"]]
        return {"book_key": m["book_key"], "book": m["book"], "author": m["author"],
                "bab_index": m["bab_index"], "bab_title": m["bab_title"], "section": m["section"],
                "unit_key": m["unit_key"], "unit_number": unit.number,
                "text": p["text"], "score": round(float(p["score"]), 4)}
