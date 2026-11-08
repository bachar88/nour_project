-- Nour — database schema for Supabase (Postgres + pgvector).
-- Run once: Supabase dashboard → SQL Editor → paste this file → Run. Safe to run again.

create extension if not exists vector;

-- One row per unit (a فصل / paragraph block, or a whole bab in Al-Risala): what the reader shows.
create table if not exists public.units (
  key        text primary key,          -- e.g. "akhdari-05-001"
  book_key   text not null,             -- "risala" | "akhdari" | ...
  book       text not null,             -- display title, e.g. «الرسالة»
  author     text not null,
  madhhab    text not null,             -- "maliki" | "hanafi" | "shafii" | "hanbali"
  bab_index  int  not null,
  bab_title  text not null,
  section    text not null,
  number     int  not null,             -- 1..N inside its book, shown in the reader
  segments   jsonb not null             -- array of strings; unit text = segments joined by spaces
);

-- One row per chunk (a few segments of a unit), with its BGE-M3 embedding (1024 dimensions).
create table if not exists public.chunks (
  id         text primary key,          -- e.g. "akhdari-05-001-00"
  unit_key   text not null references public.units(key) on delete cascade,
  madhhab    text not null,
  book_key   text not null,
  seg_start  int  not null,
  seg_end    int  not null,
  text       text not null,
  embedding  vector(1024) not null
);

create index if not exists chunks_madhhab_idx on public.chunks (madhhab);
create index if not exists units_book_idx on public.units (book_key, bab_index, number);
-- HNSW index = fast approximate nearest-neighbour search on the vectors (cosine distance)
create index if not exists chunks_embedding_idx on public.chunks using hnsw (embedding vector_cosine_ops);

-- Small key/value table: fingerprint of the last indexing run, etc.
create table if not exists public.index_meta (
  key   text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

-- Security: Row Level Security ON and no policies → the public "anon" key can read nothing.
-- Only the backend, with the secret/service_role key, can read and write (that key bypasses RLS).
alter table public.units      enable row level security;
alter table public.chunks     enable row level security;
alter table public.index_meta enable row level security;

-- Vector search used by the backend: the `match_count` chunks closest to the question, for one madhhab.
-- similarity = cosine similarity in [-1, 1] (1 = same direction).
create or replace function public.match_chunks(
  query_embedding vector(1024),
  filter_madhhab  text,
  match_count     int default 20
)
returns table (
  id text, unit_key text, book_key text, seg_start int, seg_end int, text text, similarity float
)
language sql stable
set search_path = public, extensions
as $$
  select c.id, c.unit_key, c.book_key, c.seg_start, c.seg_end, c.text,
         1 - (c.embedding <=> query_embedding) as similarity
  from public.chunks c
  where c.madhhab = filter_madhhab
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

-- Keep the function off the public API: only the secret/service_role key may call it.
revoke execute on function public.match_chunks(vector, text, int) from public, anon, authenticated;
grant  execute on function public.match_chunks(vector, text, int) to service_role;
