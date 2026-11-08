# نور — Nour

Ask questions about **Salat** and get answers taken only from Maliki texts, **Al-Risala** (Ibn Abi Zayd al-Qayrawani) and **Mukhtasar al-Akhdari**. Every answer quotes its evidence word for word and opens the book at that passage.

**Deploying:** see [DEPLOY.md](DEPLOY.md). Everything is hosted for free: Vercel, Supabase, Cloudflare Workers AI and Groq.

```
nour_project/
├── api/index.py            Vercel entry point → backend/app/main.py
├── vercel.json             builds the site, routes /api/* to FastAPI
├── requirements.txt        API runtime deps (fastapi, httpx, python-dotenv)
├── backend/
│   ├── app/
│   │   ├── config.py       all settings (environment variables)
│   │   ├── chunking.py     books → babs → units → segments → chunks, quote matching
│   │   ├── rag.py          retrieval, adaptive selection, prompt, grounding check
│   │   ├── store.py        Supabase (REST): units, vector search, writes
│   │   ├── models.py       Cloudflare BGE-M3 + Groq clients (plain HTTP)
│   │   ├── dev_fakes.py    offline stand-ins (tests + demo mode)
│   │   └── main.py         API endpoints
│   ├── supabase/schema.sql tables, match_chunks(), security
│   ├── scripts/            index_supabase.py, evaluate.py, export_corpus.py
│   ├── data/               the source texts (.txt)
│   └── tests/              pytest, fully offline
├── notebooks/nour_admin.ipynb   Colab: index the books + evaluate
├── .github/workflows/keepalive.yml   daily ping so Supabase never pauses
└── frontend/               React + Vite, RTL UI
```

## How an answer is built

1. **Chunking per book** (at indexing time). Al-Risala has almost no full stops and its page breaks fall mid-sentence, so pages are re-joined and split before ruling markers («ومن», «وأما»…). Al-Akhdari is split on `فصل:` / `(وسننه)` / `(وفضائله)`. Each chunk is embedded with BGE-M3 (Cloudflare) and stored in Supabase.
2. **Retrieve.** The question is embedded with the same BGE-M3, and `match_chunks()` returns the 20 closest chunks for the chosen madhhab.
3. **Adaptive selection** (no fixed TOP_K). Keep chunks within `COSINE_MARGIN` of the best one (max 3), merge overlapping chunks, and cap the context at 2,200 characters.
4. **Score gate.** If the best chunk is below `MIN_COSINE_SCORE`, abstain without calling the LLM.
5. **Extractive prompt.** gpt-oss-120b (low reasoning, reasoning hidden) must quote its evidence «…» word for word with the passage number.
6. **Grounding check.** Each quote is searched for in the retrieved text (ignoring diacritics and punctuation). Found → «موثّق في النص» plus its exact position for highlighting. Not found → flagged as a likely hallucination.

## Working on it

**Demo mode** (no keys, no database; fake models, answers are not real; the UI shows «وضع تجريبي»):

```bash
cd backend && pip install -r requirements.txt
NOUR_DEMO=1 uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev        # http://localhost:5173
```

**Against the real services:** copy `backend/.env.example` to `backend/.env`, fill in the keys, and run `uvicorn app.main:app --port 8000` without `NOUR_DEMO`.

**Tests** (offline: Supabase, Cloudflare and Groq are faked; the SQL schema was checked on Postgres + pgvector):

```bash
cd backend && pytest -q
```

**Browser-only preview** (one HTML file: BM25 + Claude instead of the backend):

```bash
cd backend && python -m scripts.export_corpus && cd ../frontend && npm run build:preview
```

## API

| Method | Path | What it returns |
|---|---|---|
| GET | `/api/health` (`?deep=1` also queries the DB) | status, model, missing env variables if any |
| GET | `/api/madhahib` | the 4 madhahib and which are available (Maliki for now) |
| GET | `/api/books?madhhab=maliki` | books and their babs (for «مكتبتي») |
| GET | `/api/books/{book}/babs/{i}` | all units of a bab + prev/next (for the reader) |
| POST | `/api/ask` `{question, madhhab}` | answer, evidence (quote, unit, spans to highlight), grounding, passages, `top_score` |

## Next steps

- Tune `MIN_COSINE_SCORE` / `COSINE_MARGIN` with the Colab evaluation (step 4) once the real index exists.
- Add the other madhahib (one source pair each: see the end of DEPLOY.md).
- Add the Baghawi tafsir as its own index (same `chunks` table with its own `madhhab`/source key, or a second table).
