"""Compare two versions of the Al-Akhdari chunking — the one on `main` (old) and the one in this
checkout (new) — with the real BGE-M3 embeddings and, optionally, the real Groq answers.

Read-only: both versions are embedded and searched IN MEMORY. Nothing is written to Supabase,
so the live site is not touched. Al-Risala is the same in both, so only Al-Akhdari can differ.

In the admin notebook (after steps 1 and 2):
    from scripts.compare_chunking import run
    report = run()            # retrieval only: Cloudflare embeddings, no Groq calls (~1 min)
    report = run(llm=True)    # + answers, only for questions whose passages changed (~2,000 tokens each)
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import time
from pathlib import Path

from app.chunking import build_corpus, find_quote_spans
from app.config import settings
from app.dev_fakes import MemoryStore
from app.rag import RagEngine

BACKEND = Path(__file__).resolve().parents[1]
GOLDEN = BACKEND / "eval" / "golden.jsonl"
LINE = "─" * 90

# The 17 cases proposed from the 50-question run (not yet in eval/golden.jsonl).
PROPOSED = [
    ("متى يبدأ وقت صلاة العصر ومتى ينتهي؟", [["وأول وقت العصر آخر وقت الظهر وآخره أن يصير ظل كل شيء مثليه"]]),
    ("ما صفة الإقامة؟", [["والإقامة وتر الله أكبر الله أكبر"]]),
    ("ما هي فرائض التيمم؟", [["النية والصعيد الطاهر، ومسح الوجه ومسح اليدين إلى الكوعين"]]),
    ("ما الذي يكره فعله في الصلاة؟", [["ويكره الالتفات في الصلاة، وتغميض العينين"]]),
    ("ماذا يقول المصلي في الركوع والسجود؟", [["والتسبيح في الركوع والدعاء في السجود", "وقل إن شئت سبحان ربي العظيم وبحمده"]]),
    ("متى يكون القنوت في صلاة الصبح؟", [["والقنوت سرا قبل الركوع وبعد السورة في ثانية الصبح", "غير أنك تقنت بعد الركوع وإن شئت قنت قبل الركوع"]]),
    ("كيف يجلس المصلي في التشهد؟", [["فإذا جلست بعد السجدتين نصبت رجلك اليمنى وبطون أصابعها إلى الأرض وثنيت اليسرى"]]),
    ("كم تسليمة يسلم المأموم؟", [["والتسليمة الثانية والثالثة للمأموم"]]),
    ("من أولى الناس بالإمامة؟", [["ويؤم الناس أفضلهم وأفقههم"]]),
    ("بماذا يدرك المسبوق فضل الجماعة؟", [["ومن أدرك ركعة فأكثر فقد أدرك الجماعة"]]),
    ("ما حكم من تكلم في الصلاة ساهيا؟", [["ومن تكلم ساهيا سجد بعد السلام"]]),
    ("هل يسجد المسبوق مع الإمام لسهوه؟", [["والمسبوق إن أدرك مع الإمام أقل من ركعة فلا يسجد معه"], ["وإن أدرك ركعة كاملة أو أكثر سجد معه القبلي وأخر البعدي"]]),
    ("ماذا يفعل من نسي ركعة وتذكرها بعد السلام؟", [["ومن انصرف من الصلاة ثم ذكر أنه بقي عليه شيء منها فليرجع إن كان بقرب ذلك"]]),
    ("كيف تقضى الصلوات الفائتة؟", [["ذكر صلاة صلاها متى ما ذكرها على نحو ما فاتته", "يجب قضاء ما في الذمة من الصلوات"]]),
    ("هل يجوز لمن عليه صلوات فائتة أن يصلي النوافل؟", [["ولا يتنفل من عليه القضاء"]]),
    ("كيف تصلى صلاة الخوف في السفر؟", [["وصلاة الخوف في السفر إذا خافوا العدو أن يتقدم الإمام بطائفة"]]),
    ("نسيت الفاتحة في ركعة من صلاة الظهر، شنوة نعمل؟", [["بخلاف الفريضة فإنه يلغي تلك الركعة ويزيد أخرى"]]),
]

# The 50 questions run on the site on 20/11 (48–50 are outside the books).
QUESTIONS_50 = [
    "ما هو الوقت المختار لصلاة الظهر؟", "متى يبدأ وقت صلاة العصر ومتى ينتهي؟", "هل لصلاة المغرب وقت واحد أم أكثر؟",
    "ما هو الشفق الذي يدخل به وقت العشاء؟", "في أي الأوقات لا تجوز صلاة النافلة؟", "ما حكم الأذان في المساجد؟",
    "هل يجوز الأذان قبل دخول الوقت؟", "ما صفة الإقامة؟", "هل على المرأة أذان أو إقامة؟", "ما هي فرائض الوضوء؟",
    "ما هي نواقض الوضوء؟", "ماذا يفعل من نسي فرضا من فرائض الوضوء؟", "ما هي فرائض الغسل؟",
    "متى يجوز للحاضر الصحيح أن يتيمم؟", "ما هي فرائض التيمم؟", "كم أكثر مدة الحيض للمبتدأة؟", "كم أكثر مدة النفاس؟",
    "ما هي شروط الصلاة؟", "ما هي عورة المرأة في الصلاة؟", "ماذا يفعل من صلى إلى غير القبلة خطأ؟", "ما هي سنن الصلاة؟",
    "ما هي فضائل الصلاة؟", "ما الذي يكره فعله في الصلاة؟", "كيف يصلي المريض الذي لا يقدر على القيام؟",
    "ماذا يقول المصلي في الركوع والسجود؟", "متى يكون القنوت في صلاة الصبح؟", "كيف يجلس المصلي في التشهد؟",
    "كم تسليمة يسلم المأموم؟", "من أولى الناس بالإمامة؟", "أين يقف الرجل الواحد إذا صلى مع الإمام؟",
    "بماذا يدرك المسبوق فضل الجماعة؟", "متى يكون سجود السهو بعد السلام؟", "ما حكم من تكلم في الصلاة ساهيا؟",
    "ما حكم من نفخ في صلاته؟", "هل يسجد المسبوق مع الإمام لسهوه؟", "ماذا يفعل من نسي ركعة وتذكرها بعد السلام؟",
    "كيف تقضى الصلوات الفائتة؟", "هل يجوز لمن عليه صلوات فائتة أن يصلي النوافل؟",
    "متى يتم المسافر صلاته إذا نوى الإقامة في مكان؟", "على من تجب صلاة الجمعة؟", "ما حكم الغسل لصلاة الجمعة؟",
    "كيف تصلى صلاة الخوف في السفر؟", "ما حكم صلاة العيدين وهل لها أذان وإقامة؟", "كيف تصلى صلاة خسوف الشمس؟",
    "كم تكبيرة في صلاة الجنازة وأين يقف الإمام من الميت؟", "نسيت الفاتحة في ركعة من صلاة الظهر، شنوة نعمل؟",
    "الإمام قام لركعة خامسة، نقعد ولا نقوم معاه؟", "ما مقدار زكاة الفطر؟", "ما حكم صيام يوم عاشوراء؟",
    "ما هي شروط صحة البيع؟",
]


class CachedEmbedder:
    """Embeds each distinct text once (Al-Risala and the questions are shared by both versions)."""
    def __init__(self, inner):
        self.inner, self.cache = inner, {}

    def encode(self, texts):
        todo = list(dict.fromkeys(t for t in texts if t not in self.cache))
        if todo:
            for t, v in zip(todo, self.inner.encode(todo)):
                self.cache[t] = v
        return [self.cache[t] for t in texts]


def old_akhdari_text(ref: str = "origin/main") -> str:
    """Al-Akhdari as it is on `main` (fetched into the shallow clone if needed)."""
    path = "backend/data/al_akhdari.txt"
    try:
        return subprocess.run(["git", "show", f"{ref}:{path}"], cwd=BACKEND, check=True,
                              capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "main:refs/remotes/origin/main"],
                       cwd=BACKEND, check=True)
        return subprocess.run(["git", "show", f"{ref}:{path}"], cwd=BACKEND, check=True,
                              capture_output=True, text=True).stdout


def old_settings(old_text: str):
    tmp = Path("/tmp/al_akhdari_main.txt")
    tmp.write_text(old_text, encoding="utf-8")
    sources = tuple(dataclasses.replace(s, path=tmp, paragraph_units=False) if s.key == "akhdari" else s
                    for s in settings.sources)
    return dataclasses.replace(settings, sources=sources)


def cases() -> list[dict]:
    golden = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = [{"question": c["question"], "groups": c.get("expected_groups") or [c["expected_evidence"]],
            "from": "golden"} for c in golden if not c.get("out_of_scope")]
    seen = {c["question"] for c in out}
    out += [{"question": q, "groups": g, "from": "proposed"} for q, g in PROPOSED if q not in seen]
    return out


def hit(case: dict, passages: list[dict]) -> bool:
    return all(any(find_quote_spans(p["text"], e) for p in passages for e in g) for g in case["groups"])


def _label(p: dict) -> str:
    m = p["metadata"]
    return f"{m['book_key']}:{m['unit_key'].split('-', 1)[1]}"


def run(llm: bool = False, sleep: float = 15.0, embedder=None, llm_client=None) -> dict:
    if embedder is None:
        from app.models import CloudflareEmbedder
        embedder = CloudflareEmbedder(settings)
    if llm and llm_client is None:
        from app.models import GroqLLM
        llm_client = GroqLLM(settings)
    emb = CachedEmbedder(embedder)

    engines = {}
    for name, s in (("old", old_settings(old_akhdari_text())), ("new", settings)):
        corpus = build_corpus(s)
        n_units = sum(u.book_key == "akhdari" for u in corpus.units.values())
        n_chunks = sum(c.metadata["book_key"] == "akhdari" for c in corpus.chunks)
        print(f"{name}: Al-Akhdari {n_units} units, {n_chunks} chunks")
        engines[name] = RagEngine(corpus, s, emb, MemoryStore(corpus, emb), llm_client)

    # 1. Retrieval score on the golden + proposed cases
    rows = []
    for c in cases():
        r = {k: e.retrieve(c["question"], "maliki") for k, e in engines.items()}
        rows.append({**c, "old": hit(c, r["old"]["passages"]), "new": hit(c, r["new"]["passages"]),
                     "top_old": r["old"]["candidates"][0]["score"], "top_new": r["new"]["candidates"][0]["score"]})
    print(f"\n{LINE}\n1. Retrieval — the expected sentence is in the passages sent to the model")
    for src in ("golden", "proposed"):
        sub = [x for x in rows if x["from"] == src]
        print(f"   {src:8s} ({len(sub)} cases): old {sum(x['old'] for x in sub)}/{len(sub)}  →  "
              f"new {sum(x['new'] for x in sub)}/{len(sub)}")
    for x in rows:
        if x["old"] != x["new"]:
            print(f"   {'✅ gained' if x['new'] else '❌ lost  '}  {x['question']}  "
                  f"(top {x['top_old']:.3f} → {x['top_new']:.3f})")

    # 2. The 50 questions: which ones now send different passages to the model
    print(f"\n{LINE}\n2. The 50 questions — passages sent to the model, old → new (only the changed ones)")
    changed = []
    for n, q in enumerate(QUESTIONS_50, 1):
        r = {k: e.retrieve(q, "maliki") for k, e in engines.items()}
        old_p, new_p = r["old"]["passages"], r["new"]["passages"]
        if [p["text"] for p in old_p] != [p["text"] for p in new_p]:
            changed.append(n)
            print(f"\n[{n}] {q}")
            for name, ps in (("old", old_p), ("new", new_p)):
                desc = ", ".join(f"{_label(p)} ({p['score']:.3f}, {len(p['text'])} chars)" for p in ps)
                print(f"    {name}: {desc or 'nothing sent (below MIN_COSINE_SCORE)'}")
    print(f"\n{len(changed)}/50 questions send different passages; the other {50 - len(changed)} are unchanged.")

    # 3. Optional: the real answers, only where the passages changed
    answers = []
    if llm:
        print(f"\n{LINE}\n3. Answers (Groq) for the {len(changed)} changed questions — old vs new")
        first = True
        for n in changed:
            q = QUESTIONS_50[n - 1]
            print(f"\n[{n}] {q}")
            for name, e in engines.items():
                if not first:
                    time.sleep(sleep)  # Groq free tier: 8,000 tokens/minute
                first = False
                a = e.ask(q, "maliki")
                quotes = "  ".join(f"{'✓' if ev['found'] else '✗'}«{ev['quote'][:90]}»" for ev in a["evidence"])
                print(f"    {name}: {a['answer'][:200]}\n         {quotes}")
                answers.append({"n": n, "version": name, **{k: a[k] for k in ("answer", "grounding", "abstained")}})
    return {"retrieval": rows, "changed": changed, "answers": answers}


if __name__ == "__main__":
    import sys
    run(llm="--llm" in sys.argv)
