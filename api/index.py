"""Vercel entry point: exposes the FastAPI app from backend/app as a serverless function.
vercel.json sends every /api/* request here; FastAPI still sees the original path (/api/ask, ...)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401
