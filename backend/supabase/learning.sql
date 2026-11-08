-- Nour — tables for the learning loop (feedback → corrections → better answers; evaluation history).
-- Run once AFTER schema.sql: Supabase → SQL Editor → paste → Run. Safe to run again.

-- 1. What users report under an answer (👍 / 👎, comment, the sentence they picked as correct).
create table if not exists public.feedback (
  id               bigint generated always as identity primary key,
  created_at       timestamptz not null default now(),
  question         text not null,
  madhhab          text not null,
  rating           smallint not null check (rating in (-1, 1)),   -- -1 = 👎, 1 = 👍
  comment          text,
  correct_unit_key text,                                          -- plain text: units are re-created on re-index
  correct_quote    text,                                          -- sentence picked in the reader
  answer           text,                                          -- what the user saw
  evidence         jsonb,
  passages         jsonb,
  status           text not null default 'new' check (status in ('new', 'accepted', 'rejected'))
);
create index if not exists feedback_status_idx on public.feedback (status, created_at desc);

-- 2. Reviewed corrections, shown to the model as worked examples for similar questions.
create table if not exists public.corrections (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  madhhab     text not null,
  question    text not null,
  answer      text not null,
  evidence    jsonb not null,             -- array of the correct sentences
  embedding   vector(1024) not null,      -- BGE-M3 vector of the question
  feedback_id bigint references public.feedback(id) on delete set null
);
create index if not exists corrections_embedding_idx on public.corrections using hnsw (embedding vector_cosine_ops);

-- 3. One row per evaluation run, to compare versions over time.
create table if not exists public.eval_runs (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  label      text,                        -- e.g. "prompt v2, effort medium"
  settings   jsonb not null,              -- model, thresholds, prompt hash…
  scores     jsonb not null,              -- retrieval_hit, evidence_hit, abstain_ok…
  details    jsonb not null               -- per-question results
);

alter table public.feedback    enable row level security;
alter table public.corrections enable row level security;
alter table public.eval_runs   enable row level security;

create or replace function public.match_corrections(
  query_embedding vector(1024),
  filter_madhhab  text,
  match_count     int default 3
)
returns table (id bigint, question text, answer text, evidence jsonb, similarity float)
language sql stable
set search_path = public, extensions
as $$
  select c.id, c.question, c.answer, c.evidence, 1 - (c.embedding <=> query_embedding) as similarity
  from public.corrections c
  where c.madhhab = filter_madhhab
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

revoke execute on function public.match_corrections(vector, text, int) from public, anon, authenticated;
grant  execute on function public.match_corrections(vector, text, int) to service_role;
