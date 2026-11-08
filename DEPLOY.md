# Deploying Nour — free, fully hosted

```
Browser ─► Vercel (React site + FastAPI in api/index.py, same domain)
             ├─► Cloudflare Workers AI : BGE-M3 → question vector
             ├─► Supabase (pgvector)   : match_chunks() → closest chunks + book texts
             └─► Groq                  : openai/gpt-oss-120b → answer with quoted evidence
Colab (notebooks/nour_admin.ipynb): books → chunks → Cloudflare BGE-M3 → Supabase
GitHub Actions: daily ping so the free Supabase project never pauses
```

Nothing runs on your computer. Five free accounts: **GitHub** (have it), **Supabase**, **Cloudflare**, **Groq** (have it), **Vercel**.

## 1. Push the code

The Colab notebook and Vercel both read the code from GitHub, so push first:

```bash
git push -u origin main
```

The repo belongs to `bachar88`: you need to be a collaborator (or the owner pushes).

## 2. Supabase: database (≈5 min)

1. supabase.com → **New project** (any name, e.g. `nour`; choose a region close to Tunisia, e.g. Frankfurt). Keep the database password somewhere safe.
2. **SQL Editor** → **New query** → paste all of `backend/supabase/schema.sql` → **Run**. It creates `units`, `chunks`, `index_meta`, the `match_chunks()` function and turns Row Level Security on.
3. **Project Settings → API**: copy the **Project URL** and the **secret key** (`sb_secret_…`; on older projects: the `service_role` key).
   ⚠ This key bypasses all security: put it only in Colab Secrets and Vercel, never in the frontend or in Git.

## 3. Cloudflare: embeddings (≈3 min)

1. dash.cloudflare.com (free account) → **Workers & Pages** → copy the **Account ID** (right column).
2. **My Profile → API Tokens → Create Token** → template **Workers AI** → Continue → Create → copy the token.

## 4. Index the books (Colab, ≈2 min)

1. Open `notebooks/nour_admin.ipynb` in Colab (File → Open notebook → GitHub tab → `bachar88/nour_project`).
2. Add the 5 Secrets listed at the top of the notebook (🔑 icon, turn on *Notebook access*).
3. Run steps 1 → 4. Step 3 fills Supabase. Step 4 prints, per test question, the best similarity score and whether the right text was found, then **suggests a `MIN_COSINE_SCORE`**. Note it for step 5.

## 5. Vercel: site + API (≈5 min)

1. vercel.com → sign in with GitHub → **Add New → Project** → import `nour_project`.
   (If the repo doesn't appear: the GitHub account that owns it must allow the Vercel app, or create the Vercel project from that account.)
2. Leave Framework Preset / build settings as they are: `vercel.json` sets them.
3. **Environment Variables**: add
   `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `GROQ_API_KEY`,
   and `MIN_COSINE_SCORE` = the value suggested in step 4.
4. **Deploy**. Then open `https://<your-project>.vercel.app/api/health?deep=1`. You should see `"db": "ok"` and the number of units.
   If you see `"misconfigured"`, the `missing` list names the variable to add (then **Deployments → Redeploy**).

## 6. Keep-alive (≈1 min)

GitHub repo → **Settings → Secrets and variables → Actions → Variables → New repository variable**:
`NOUR_URL` = `https://<your-project>.vercel.app` (no trailing slash).
Then **Actions → keep-alive → Run workflow** once to test it. It then runs every day.

GitHub stops scheduled workflows in a repo with no commits for 60 days: re-enable it from the Actions tab if that happens.

## Free limits to keep in mind

| Service | Free limit | What it means for Nour |
|---|---|---|
| Groq `openai/gpt-oss-120b` | 30 requests/min, 1,000/day, 8,000 tokens/min, 200,000 tokens/day | ≈2,000 tokens per question → **≈4 questions/minute and ≈100/day** in total |
| Cloudflare Workers AI | 10,000 Neurons/day | Millions of embedding tokens/day: not a constraint |
| Supabase | 500 MB database, pauses after 7 idle days | Today's index is under 1 MB; the keep-alive job prevents the pause |
| Vercel Hobby | personal, non-commercial projects | Fine for Nour now; a paid plan would be needed for commercial use |

## Updating

- **Code**: push to `main` → Vercel redeploys automatically.
- **Books or chunking settings**: push, then run the Colab notebook again (steps 1–4). It re-indexes only if something changed (`--force` to rebuild anyway). The site picks up the new texts when its serverless instance restarts (within minutes), or right away after a **Redeploy**.
- **Thresholds** (`MIN_COSINE_SCORE`, `COSINE_MARGIN`, `MAX_K`…): change them in Vercel → Environment Variables → Redeploy. No code change.

## Adding a madhhab or a book

1. Put the `.txt` in `backend/data/` and add a `Source(...)` line in `backend/app/config.py` (`sources`).
2. For a new madhhab, set `"available": True` for it in `MADHAHIB` (same file).
3. Push, then run the Colab notebook.
