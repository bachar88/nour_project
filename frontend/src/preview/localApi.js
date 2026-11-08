// Browser-only stand-in for the FastAPI backend, used by `npm run build:preview` (artifact build).
// Same methods as ../api.js. Differences from the real backend (shown on the page):
//   - retrieval: BM25 keyword search with light Arabic stemming (instead of BGE-M3 + reranker)
//   - answers:   Claude via the artifact's `sample` capability (instead of Groq gpt-oss-120b)
// Selection, merging, prompt, quote check and highlight spans follow backend/app/rag.py.
import corpus from "./corpus.json";

const MAX_K = 3;
const REL_CUTOFF = 0.5;     // keep chunks with score >= 50% of the best
const MIN_COVERAGE = 0.6;   // best chunk must contain >= 60% of the question's keywords, else abstain
const MAX_CONTEXT_CHARS = 2200;
const ABSTAIN_TEXT = "لم يرد في النص ما يجيب عن هذا السؤال.";

// ---------- text ----------
const TASHKEEL = /[ؐ-ًؚ-ٰٟۖ-ۭـ]/g;
export const normalizeAr = (t) => t.replace(TASHKEEL, "").replace(/[إأآٱ]/g, "ا").replace(/\s+/g, " ").trim();

const STOP = new Set(["ما", "ماذا", "هي", "هو", "في", "من", "على", "عن", "الى", "الي", "ان", "كم", "متى", "هل",
  "حكم", "كيف", "التي", "الذي", "ذلك", "هذا", "هذه", "او", "ثم", "لا", "لم", "مع", "عدد", "يفعل", "اذا", "قد", "كان"]);

function stem(w) {
  let s = w.replace(/ة$/, "ه");
  if (/^(و|ف)?(ب|ك|ل)?ال/.test(s) && s.replace(/^(و|ف)?(ب|ك|ل)?ال/, "").length >= 2) s = s.replace(/^(و|ف)?(ب|ك|ل)?ال/, "");
  else if (s.startsWith("لل") && s.length > 4) s = s.slice(2);
  else if (/^[وف]/.test(s) && s.length > 4) s = s.slice(1);
  if (s.length > 4) s = s.replace(/(ات|ون|ين|ها|هم)$/, "");
  if (s.length > 3) s = s.replace(/ه$/, "");
  return s;
}

function terms(text) {
  return normalizeAr(text).replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/)
    .filter((w) => w.length > 1 && !STOP.has(w)).map(stem).filter((w) => w.length > 1 && !STOP.has(w));
}

// ---------- index (BM25) ----------
const units = corpus.units;
const unitText = (key) => units[key].segments.join(" ");
const docs = corpus.chunks.map((c) => {
  const u = units[c.unit_key];
  const text = u.segments.slice(c.seg_start, c.seg_end).join(" ");
  const toks = terms(`${u.bab_title} ${u.section} ${text}`);
  const tf = new Map();
  toks.forEach((t) => tf.set(t, (tf.get(t) || 0) + 1));
  return { ...c, text, tf, len: toks.length };
});
const avgLen = docs.reduce((a, d) => a + d.len, 0) / docs.length;
const df = new Map();
docs.forEach((d) => d.tf.forEach((_, t) => df.set(t, (df.get(t) || 0) + 1)));
const idf = (t) => Math.log(1 + (docs.length - (df.get(t) || 0) + 0.5) / ((df.get(t) || 0) + 0.5));

export function retrieve(question) {
  const q = [...new Set(terms(question))];
  if (!q.length) return { candidates: [], passages: [] };
  const k1 = 1.5, b = 0.75;
  const cands = docs.map((d) => {
    let score = 0, hit = 0;
    for (const t of q) {
      const f = d.tf.get(t) || 0;
      if (!f) continue;
      hit += 1;
      score += idf(t) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * d.len / avgLen));
    }
    return { doc: d, score, coverage: hit / q.length };
  }).filter((c) => c.score > 0).sort((a, b2) => b2.score - a.score).slice(0, 20);
  return { candidates: cands, passages: selectContext(cands) };
}

function selectContext(cands) {
  if (!cands.length || cands[0].coverage < MIN_COVERAGE) return []; // score gate
  const top = cands[0].score;
  const kept = cands.filter((c) => c.score >= REL_CUTOFF * top).slice(0, MAX_K);
  const out = [];
  let total = 0;
  for (const p of mergeHits(kept)) {
    if (out.length && total + p.text.length > MAX_CONTEXT_CHARS) break;
    out.push(p);
    total += p.text.length;
  }
  return out;
}

function mergeHits(hits) {
  const groups = new Map();
  for (const h of hits) {
    const k = h.doc.unit_key;
    const g = groups.get(k) || { unitKey: k, score: h.coverage, idx: new Set() };
    g.score = Math.max(g.score, h.coverage);
    for (let i = h.doc.seg_start; i < h.doc.seg_end; i++) g.idx.add(i);
    groups.set(k, g);
  }
  return [...groups.values()].map((g) => {
    const segs = units[g.unitKey].segments;
    const runs = [];
    [...g.idx].sort((a, b) => a - b).forEach((i) => {
      const last = runs[runs.length - 1];
      if (last && i === last[last.length - 1] + 1) last.push(i);
      else runs.push([i]);
    });
    const text = runs.map((r) => r.map((i) => segs[i]).join(" ")).join(" … ");
    return { unitKey: g.unitKey, text, score: g.score };
  }).sort((a, b) => b.score - a.score);
}

// ---------- quote matching (port of chunking.find_quote_spans) ----------
function wordIndex(text) {
  const out = [], pos = [];
  let pending = false;
  for (let i = 0; i < text.length; i++) {
    let ch = text[i];
    if (/[ؐ-ًؚ-ٰٟۖ-ۭـ]/.test(ch)) continue;
    if (/[إأآٱ]/.test(ch)) ch = "ا";
    if (/[\p{L}\p{N}_]/u.test(ch)) {
      if (pending && out.length) { out.push(" "); pos.push(i); }
      pending = false;
      out.push(ch); pos.push(i);
    } else pending = true;
  }
  return [out.join(""), pos];
}

export function findQuoteSpans(text, quote) {
  const [norm, pos] = wordIndex(text);
  const padded = ` ${norm} `;
  const spans = [];
  for (const piece of quote.split(/\.\.\.|…/)) {
    const [np] = wordIndex(piece);
    if (!np) continue;
    const idx = padded.indexOf(` ${np} `);
    if (idx < 0) return null;
    spans.push([pos[idx], pos[idx + np.length - 1] + 1]);
  }
  return spans.length ? spans : null;
}

// ---------- generation ----------
const SYSTEM_PROMPT = `أنت مساعد يستخرج الأحكام من نصوص فقهية من المذهب المالكي، ولست مفتيًا.
القواعد:
1. اعتمد فقط على المقاطع المرقّمة المعطاة، ولا تستعمل أي معلومة من خارجها.
2. أجب عن السؤال المحدد فقط، وتجاهل باقي المسائل الموجودة في المقاطع.
3. لا تُضف حكمًا أو وصفًا (واجب، سنة، فضيلة، مكروه...) إلا إذا ورد حرفيًا في النص.
4. انقل الدليل من المقطع حرفيًا بين «» دون تغيير أي كلمة، ثم اذكر رقم المقطع بين معقوفين.
5. إن ذكر الكتابان المسألة بعبارتين مختلفتين فاذكر عبارة كل كتاب مع رقمه.
6. إن لم تُجب المقاطع عن السؤال صراحة، اكتب هذه الجملة فقط: ${ABSTAIN_TEXT}

صيغة الإجابة:
الجواب: جملة أو جملتان.
الدليل: «نص منقول حرفيًا» [رقم المقطع]`;

const bookOf = (key) => corpus.books.find((b) => b.key === key);

function publicPassage(p) {
  const u = units[p.unitKey];
  const book = bookOf(u.book_key);
  return { book_key: u.book_key, book: book.title, author: book.author, bab_index: u.bab_index,
    bab_title: u.bab_title, section: u.section, unit_key: p.unitKey, unit_number: u.number,
    text: p.text, score: Math.round(p.score * 1000) / 1000 };
}

function buildPrompt(question, passages) {
  const ctx = passages.map((p, i) => `[${i + 1}] (${p.book} — ${p.bab_title})\n${p.text}`).join("\n\n");
  return `${SYSTEM_PROMPT}\n\nالمقاطع:\n${ctx}\n\nالسؤال: ${question}`;
}

function parseAnswer(raw, passages) {
  const m = raw.match(/الجواب\s*:\s*([\s\S]*?)(?=\n\s*الدليل\s*:|$)/);
  const answer = (m ? m[1] : raw.split("«")[0]).trim() || raw.trim();
  const evidence = [...raw.matchAll(/«([^»]+)»\s*(?:\[(\d+)\])?/g)].map(([, quote, num]) => {
    const order = passages.map((_, i) => i);
    const n = Number(num);
    if (n >= 1 && n <= passages.length) { order.splice(n - 1, 1); order.unshift(n - 1); }
    const found = order.find((i) => findQuoteSpans(passages[i].text, quote));
    if (found === undefined) return { quote: quote.trim(), passage: n || null, found: false, unit_key: null, spans: [] };
    const key = passages[found].unit_key;
    return { quote: quote.trim(), passage: found + 1, found: true, unit_key: key,
      spans: findQuoteSpans(unitText(key), quote) || [] };
  });
  const grounding = !evidence.length ? "no_quote" : evidence.every((e) => e.found) ? "grounded" : "not_found";
  return { answer, evidence, grounding };
}

let samplePromise = null;
const getSample = () => {
  if (!samplePromise) samplePromise = window.claude?.use ? window.claude.use("sample").catch(() => null) : Promise.resolve(null);
  return samplePromise;
};

async function generate(question, passages) {
  const sample = await getSample();
  if (!sample) {
    const quote = passages[0].text.split(" ").slice(0, 12).join(" ");
    return { raw: `الجواب: (Claude غير متاح هنا) جواب تجريبي من المقطع الأول.\nالدليل: «${quote}» [1]`, offline: true };
  }
  try {
    const res = await sample(buildPrompt(question, passages), { cache: false });
    return { raw: res.text.trim() };
  } catch (e) {
    if (e?.code === "rate_limited") throw new Error("تم تجاوز حد الطلبات مؤقتًا، أعد المحاولة بعد قليل.");
    if (e?.code === "not_granted") throw new Error("لم يُسمح للصفحة باستعمال Claude. أعد تحميل الصفحة ووافق على الطلب.");
    throw new Error(e?.message || "تعذّر الحصول على جواب من Claude.");
  }
}

// ---------- API (same shape as backend) ----------
const delay = (v) => Promise.resolve(v);

export const api = {
  health: () => delay({ status: "ok", units: Object.keys(units).length, chunks: docs.length, preview: true,
    llm: "Claude", demo: false }),
  madhahib: () => delay([
    { key: "maliki", label: "مالكي", available: true },
    { key: "hanafi", label: "حنفي", available: false },
    { key: "shafii", label: "شافعي", available: false },
    { key: "hanbali", label: "حنبلي", available: false },
  ]),
  books: (madhhab) => delay(corpus.books.filter((b) => b.madhhab === madhhab).map((b) => ({
    key: b.key, title: b.title, author: b.author, madhhab: b.madhhab,
    babs: b.babs.map((x) => ({ index: x.index, title: x.title, units: x.unit_keys.length })),
  }))),
  bab: async (bookKey, babIndex) => {
    const book = bookOf(bookKey);
    const bab = book?.babs[babIndex];
    if (!bab) throw new Error("الباب غير موجود");
    return {
      book_key: book.key, book: book.title, author: book.author, bab_index: babIndex, bab_title: bab.title,
      prev: babIndex > 0 ? babIndex - 1 : null,
      next: babIndex + 1 < book.babs.length ? babIndex + 1 : null,
      units: bab.unit_keys.map((k) => ({ key: k, number: units[k].number, section: units[k].section, text: unitText(k) })),
    };
  },
  ask: async (question, madhhab) => {
    const t0 = performance.now();
    const passages = retrieve(question).passages.map(publicPassage);
    const base = { question, madhhab, answer: ABSTAIN_TEXT, raw: "", evidence: [], grounding: "n/a",
      abstained: null, passages, tokens: 0 };
    if (!passages.length) return { ...base, abstained: "retrieval" };
    const { raw } = await generate(question, passages);
    if (normalizeAr(raw).includes(normalizeAr(ABSTAIN_TEXT.slice(0, 20)))) {
      return { ...base, raw, abstained: "model", elapsed: (performance.now() - t0) / 1000 };
    }
    return { ...base, raw, ...parseAnswer(raw, passages), elapsed: (performance.now() - t0) / 1000 };
  },
};
