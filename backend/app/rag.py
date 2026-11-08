"""Question → BGE-M3 vector → Supabase vector search → adaptive selection → merge → LLM → quote check."""
from __future__ import annotations

import logging
import re
import time

from .chunking import Corpus, find_quote_spans, normalize_ar
from . import learning
from .config import Settings

log = logging.getLogger("nour.rag")

ABSTAIN_TEXT = "لم يرد في النص ما يجيب عن هذا السؤال."

SYSTEM_PROMPT = f"""أنت مساعد يستخرج الأحكام من نصوص فقهية من المذهب المالكي، ولست مفتيًا.

طريقة العمل:
1. حدّد ما يُسأل عنه بالضبط: حكم، أو وقت، أو عدد، أو سبب، أو شرط، أو كيفية.
2. المقطع الواحد قد يجمع مسائل كثيرة متقاربة الألفاظ. اختر الجملة التي تجيب عن السؤال فعلًا، لا الجملة التي تشترك معه في الكلمات فقط.
3. قدّم القاعدة العامة التي ينصّ عليها الكتاب على المسائل المتفرعة عنها (مثل: «ومن نسي…»، «وإن طال…»، «إلا أن…»)، ولا تذكر المتفرعات إلا إذا سأل عنها السؤال.
4. لا تكتب في الجواب إلا ما تدل عليه الجمل التي نقلتها، ولا تستعمل أي معلومة من خارج المقاطع.
5. لا تُضف حكمًا أو وصفًا (واجب، سنة، فضيلة، مكروه...) إلا إذا ورد حرفيًا في النص.
6. انقل كل جملة يقوم عليها الجواب حرفيًا بين «» دون تغيير أي كلمة، مع رقم المقطع بين معقوفين. إن احتجت جملتين فانقل الاثنتين.
7. إن ذكر الكتابان المسألة فاذكر عبارة كل كتاب مع رقمه.
8. إن لم تُجب المقاطع عن السؤال صراحة، اكتب هذه الجملة فقط: {ABSTAIN_TEXT}

صيغة الإجابة:
الجواب: جملة أو جملتان.
الدليل: «نص منقول حرفيًا» [رقم المقطع]
الدليل: «نص منقول حرفيًا» [رقم المقطع] (عند الحاجة)"""
QUOTE_RE = re.compile(r"«([^»]+)»\s*(?:\[(\d+)\])?")
EXAMPLES_HEADER = ("أمثلة محلولة من تصحيحات سابقة لأسئلة مشابهة، لتوضيح طريقة اختيار الدليل فقط. "
                   "لا تنقل منها شيئًا: انقل الدليل من المقاطع المرقّمة وحدها.")
ANSWER_RE = re.compile(r"الجواب\s*:\s*(.*?)(?=\n\s*الدليل\s*:|$)", re.S)


class RagEngine:
    """`store` needs .match(vector, madhhab, count) -> rows with id, unit_key, seg_start, seg_end, text, similarity.
    `embedder` needs .encode(texts); `llm` needs .complete(messages)."""

    def __init__(self, corpus: Corpus, settings: Settings, embedder, store, llm):
        self.corpus = corpus
        self.settings = settings
        self.embedder, self.store, self.llm = embedder, store, llm

    # ---------- retrieval ----------
    def retrieve(self, query: str, madhhab: str) -> dict:
        q_vec = self.embedder.encode([normalize_ar(query)])[0]
        rows = self.store.match(q_vec, madhhab, self.settings.fetch_k)
        cands = []
        for r in rows:
            unit = self.corpus.units.get(r["unit_key"])
            if unit is None:  # index and units out of sync: skip rather than crash
                continue
            book = self.corpus.books[unit.book_key]
            cands.append({"text": r["text"], "score": float(r["similarity"]), "metadata": {
                "book_key": unit.book_key, "book": book.title, "author": book.author,
                "bab_index": unit.bab_index, "bab_title": unit.bab_title, "section": unit.section,
                "unit_key": unit.key, "seg_start": r["seg_start"], "seg_end": r["seg_end"]}})
        cands.sort(key=lambda c: -c["score"])
        return {"candidates": cands, "passages": self.select_context(cands), "query_vector": q_vec}

    def select_context(self, cands: list[dict]) -> list[dict]:
        """Keep only chunks close to the best one (max_k), merge, and respect a size budget.
        A fixed large TOP_K feeds the model near-miss rulings, which it then mixes in."""
        if not cands:
            return []
        s, top = self.settings, cands[0]["score"]
        if top < s.min_cosine_score:  # gate: nothing relevant enough → abstain without calling the LLM
            return []
        kept = [c for c in cands if c["score"] >= top - s.cosine_margin][:s.max_k]
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
    def build_messages(query: str, passages: list[dict], examples: list[str] | None = None) -> list[dict]:
        ctx = "\n\n".join(
            f"[{i}] ({p['metadata']['book']} — {p['metadata']['bab_title']})\n{p['text']}"
            for i, p in enumerate(passages, 1))
        user = f"المقاطع:\n{ctx}\n\nالسؤال: {query}"
        if examples:
            user = (EXAMPLES_HEADER + "\n\n" + "\n\n---\n\n".join(examples) + "\n\n=====\n\n" + user)
        return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]

    # ---------- learning loop ----------
    def find_examples(self, query_vector, madhhab: str) -> list[dict]:
        """Past corrections close to this question, chosen by learning.pick_corrections.
        Returns [] when the feature is off, not written yet, or the lookup fails."""
        s = self.settings
        if not s.use_corrections or not hasattr(self.store, "match_corrections"):
            return []
        try:
            rows = self.store.match_corrections(query_vector, madhhab, max(3, s.max_correction_examples))
            return learning.pick_corrections(rows, s.correction_min_similarity, s.max_correction_examples)
        except NotImplementedError:
            log.warning("USE_CORRECTIONS is on but learning.pick_corrections is not written yet")
        except Exception:  # never let the learning loop break an answer
            log.exception("corrections lookup failed")
        return []

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
                  "passages": [self._public_passage(p) for p in passages], "tokens": 0, "corrections_used": [],
                  "top_score": round(r["candidates"][0]["score"], 4) if r["candidates"] else None}
        if not passages:
            result["abstained"] = "retrieval"
        else:
            used = self.find_examples(r["query_vector"], madhhab)
            examples = []
            for c in used:
                try:
                    examples.append(learning.format_example(c))
                except NotImplementedError:
                    log.warning("learning.format_example is not written yet: examples skipped")
                    break
            result["corrections_used"] = [c["id"] for c in used][:len(examples)]
            raw, tokens = self.llm.complete(self.build_messages(question, passages, examples))
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
