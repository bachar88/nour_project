"""All settings in one place. Every value can be overridden with an environment variable (or a .env file)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
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
    # Models
    embed_model: str = _env("EMBED_MODEL", "BAAI/bge-m3")
    rerank_model: str = _env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    use_reranker: bool = _env("USE_RERANKER", True, bool)
    device: str = _env("DEVICE", "auto")  # auto | cpu | cuda
    groq_api_key: str = _env("GROQ_API_KEY", "")
    groq_model: str = _env("GROQ_MODEL", "allam-2-7b")

    # Chunking (characters)
    chunk_target_chars: int = _env("CHUNK_TARGET_CHARS", 450, int)
    max_segment_chars: int = _env("MAX_SEGMENT_CHARS", 350, int)
    segment_overlap: int = _env("SEGMENT_OVERLAP", 1, int)
    min_chunk_chars: int = _env("MIN_CHUNK_CHARS", 30, int)

    # Retrieval / selection (replaces a fixed TOP_K)
    fetch_k: int = _env("FETCH_K", 20, int)
    max_k: int = _env("MAX_K", 3, int)
    min_rerank_score: float = _env("MIN_RERANK_SCORE", 0.10, float)
    rel_cutoff: float = _env("REL_CUTOFF", 0.50, float)
    min_cosine_score: float = _env("MIN_COSINE_SCORE", 0.45, float)
    cosine_margin: float = _env("COSINE_MARGIN", 0.05, float)
    max_context_chars: int = _env("MAX_CONTEXT_CHARS", 2200, int)

    # Generation
    temperature: float = _env("TEMPERATURE", 0.0, float)
    max_tokens: int = _env("MAX_TOKENS", 250, int)

    # Storage
    chroma_dir: Path = Path(_env("CHROMA_DIR", str(BACKEND_DIR / "chroma_db")))
    collection: str = _env("COLLECTION", "fiqh_salat")

    # Frontend origin(s) allowed by CORS, comma-separated
    cors_origins: tuple = tuple(_env("CORS_ORIGINS", "http://localhost:5173").split(","))

    sources: tuple = field(default_factory=lambda: (
        Source("risala", BACKEND_DIR / "data" / "al_risala.txt",
               "الرسالة", "ابن أبي زيد القيرواني", "maliki"),
        Source("akhdari", BACKEND_DIR / "data" / "al_akhdari.txt",
               "مختصر الأخضري", "عبد الرحمن الأخضري", "maliki"),
    ))


MADHAHIB = [
    {"key": "maliki", "label": "مالكي", "available": True},
    {"key": "hanafi", "label": "حنفي", "available": False},
    {"key": "shafii", "label": "شافعي", "available": False},
    {"key": "hanbali", "label": "حنبلي", "available": False},
]

settings = Settings()
