# نور — Nour

Ask questions about **Salat** and get answers taken only from Maliki texts, **Al-Risala** (Ibn Abi Zayd al-Qayrawani) and **Mukhtasar al-Akhdari**. Every answer quotes its evidence word for word and opens the book at that passage.

```
nour_project/
├── backend/            FastAPI + RAG (BGE-M3 → Chroma → reranker → Groq gpt-oss-120b)
│   ├── app/
│   │   ├── config.py       all settings (overridable with .env)
│   │   ├── chunking.py     books → babs → units → segments → chunks, quote matching
│   │   ├── rag.py          retrieval, adaptive selection, prompt, grounding check
│   │   ├── models.py       real model wrappers (loaded lazily)
│   │   ├── dev_fakes.py    lightweight fake models (tests + demo mode)
│   │   └── main.py         API endpoints
│   ├── data/               the two source texts (.txt)
│   └── tests/              pytest (runs offline with the fake models)
└── frontend/           React + Vite, RTL UI
    └── src/
        ├── App.jsx         state: view, messages, saved answers, open reader
        ├── api.js          calls to the backend
        └── components/     Sidebar, TopBar, ChatPanel, AnswerMessage, ReaderPanel, LibraryView, SavedView
```

## Run it

**Backend** (Python 3.10+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # then put your GROQ_API_KEY in .env
uvicorn app.main:app --port 8000
```

The first start downloads BGE-M3 and the reranker (about 4.5 GB) and builds the index (`backend/chroma_db/`). Later starts reuse it. A GPU helps but isn't required. On a weak machine, set `USE_RERANKER=false`.

**Frontend** (Node 18+), in a second terminal:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173  (calls to /api are proxied to :8000)
```

### Demo mode (UI work without models or an API key)

```bash
cd backend && NOUR_FAKE_MODELS=1 uvicorn app.main:app --port 8000
```

Starts in seconds and uses fake models. Answers only quote retrieved text and are **not real** (the UI shows «وضع تجريبي»). Use it to work on the frontend.

### Browser-only preview (one HTML file)

```bash
cd backend && python -m scripts.export_corpus     # refresh frontend/src/preview/corpus.json
cd ../frontend && npm run build:preview           # → dist-preview/index.html
```

Runs without the backend: keyword search (BM25) instead of BGE-M3 + reranker, and Claude (artifact `sample` capability) instead of Groq. Good for showing the UI. It doesn't measure gpt-oss-120b's quality.

### Tests

```bash
cd backend && pytest -q
```

## API

| Method | Path | What it returns |
|---|---|---|
| GET | `/api/health` | status, number of units/chunks, `demo` flag |
| GET | `/api/madhahib` | the 4 madhahib and which are available (Maliki for now) |
| GET | `/api/books?madhhab=maliki` | books and their babs (for «مكتبتي») |
| GET | `/api/books/{book}/babs/{i}` | all units of a bab + prev/next (for the reader) |
| POST | `/api/ask` `{question, madhhab}` | answer, evidence (quote, unit, character spans to highlight), grounding status, passages used |

## How an answer is built (same logic as the v2 notebook)

1. **Chunking per book.** Al-Risala has almost no full stops and its page breaks fall mid-sentence, so pages are re-joined and split before ruling markers («ومن», «وأما»…). Al-Akhdari is split on `فصل:` / `(وسننه)` / `(وفضائله)`.
2. **Retrieve 20 → rerank → keep only chunks scoring ≥ 50% of the best (max 3)**, merge overlapping chunks, and cap the context at 2,200 characters. No fixed TOP_K: a large one made the 7B model mix near-miss rulings into its answer.
3. **Score gate.** If nothing is relevant enough, the backend abstains without calling the LLM.
4. **Extractive prompt.** The model must quote its evidence «…» word for word with the passage number.
5. **Grounding check.** Each quote is searched for in the retrieved text (ignoring diacritics and punctuation). Found → «موثّق في النص» plus its exact position for highlighting. Not found → flagged as a likely hallucination.

All thresholds are in `backend/app/config.py` and can be changed in `.env`.

## Next steps

- Move vectors from Chroma to **Supabase pgvector**, as planned. Only `RagEngine.ensure_index` and `RagEngine.retrieve` touch the vector store.
- Add the other madhahib (one source pair each, plus an entry in `config.py` → `sources` and `MADHAHIB`).
- Add the Baghawi tafsir as a separate index.
