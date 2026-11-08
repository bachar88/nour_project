"""All settings in one place. Every value can be overridden with an environment variable
(Vercel → Project → Settings → Environment Variables, or backend/.env for local runs)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is only needed for local runs
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BACKEND_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default, cast=str):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    if cast is bool:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return cast(raw)


@dataclass(frozen=True)
class Source:
    key: str
    path: Path
    title: str
    author: str
    madhhab: str


@dataclass(frozen=True)
class Settings:
    # Supabase (vectors + texts). Use the SECRET / service_role key: server side only, never in the frontend.
    supabase_url: str = _env("SUPABASE_URL", "")
    supabase_key: str = _env("SUPABASE_SERVICE_KEY", "")

    # Cloudflare Workers AI (BGE-M3 embeddings) — same model for indexing and for questions
    cf_account_id: str = _env("CLOUDFLARE_ACCOUNT_ID", "")
    cf_api_token: str = _env("CLOUDFLARE_API_TOKEN", "")
    cf_embed_model: str = _env("CF_EMBED_MODEL", "@cf/baai/bge-m3")
    embed_dim: int = _env("EMBED_DIM", 1024, int)

    # Groq (answers)
    groq_api_key: str = _env("GROQ_API_KEY", "")
    groq_model: str = _env("GROQ_MODEL", "openai/gpt-oss-120b")
    reasoning_effort: str = _env("REASONING_EFFORT", "low")  # gpt-oss only: low | medium | high
    temperature: float = _env("TEMPERATURE", 0.0, float)
    max_tokens: int = _env("MAX_TOKENS", 1024, int)  # thinking + answer together for gpt-oss

    # Chunking (characters) — used by the indexing script
    chunk_target_chars: int = _env("CHUNK_TARGET_CHARS", 450, int)
    max_segment_chars: int = _env("MAX_SEGMENT_CHARS", 350, int)
    segment_overlap: int = _env("SEGMENT_OVERLAP", 1, int)
    min_chunk_chars: int = _env("MIN_CHUNK_CHARS", 30, int)

    # Retrieval / selection (no reranker in the hosted version: cosine similarity only)
    fetch_k: int = _env("FETCH_K", 20, int)
    max_k: int = _env("MAX_K", 3, int)
    min_cosine_score: float = _env("MIN_COSINE_SCORE", 0.45, float)  # best chunk below → abstain
    cosine_margin: float = _env("COSINE_MARGIN", 0.06, float)        # keep chunks within this of the best
    max_context_chars: int = _env("MAX_CONTEXT_CHARS", 2200, int)

    # Frontend origin(s) allowed by CORS, comma-separated (not needed when site + API share a domain)
    cors_origins: tuple = tuple(_env("CORS_ORIGINS", "http://localhost:5173").split(","))

    # Books indexed by scripts/index_supabase.py
    sources: tuple = field(default_factory=lambda: (
        Source("risala", BACKEND_DIR / "data" / "al_risala.txt",
               "الرسالة", "ابن أبي زيد القيرواني", "maliki"),
        Source("akhdari", BACKEND_DIR / "data" / "al_akhdari.txt",
               "مختصر الأخضري", "عبد الرحمن الأخضري", "maliki"),
    ))

    def missing(self) -> list[str]:
        """Names of required environment variables that are not set."""
        required = {"SUPABASE_URL": self.supabase_url, "SUPABASE_SERVICE_KEY": self.supabase_key,
                    "CLOUDFLARE_ACCOUNT_ID": self.cf_account_id, "CLOUDFLARE_API_TOKEN": self.cf_api_token,
                    "GROQ_API_KEY": self.groq_api_key}
        return [k for k, v in required.items() if not v]


MADHAHIB = [
    {"key": "maliki", "label": "مالكي", "available": True},
    {"key": "hanafi", "label": "حنفي", "available": False},
    {"key": "shafii", "label": "شافعي", "available": False},
    {"key": "hanbali", "label": "حنبلي", "available": False},
]

settings = Settings()
