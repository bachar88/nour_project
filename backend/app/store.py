"""Supabase access through its REST API (PostgREST) with plain httpx — no heavy SDK.

Tables and the match_chunks() function are defined in backend/supabase/schema.sql."""
from __future__ import annotations

import httpx

from .config import Settings


def vector_literal(vec) -> str:
    """pgvector accepts vectors as text: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"


class SupabaseStore:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        if not settings.supabase_url or not settings.supabase_key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set")
        key = settings.supabase_key
        headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):  # legacy service_role JWT also needs the Authorization header
            headers["Authorization"] = f"Bearer {key}"
        self.http = client or httpx.Client(
            base_url=settings.supabase_url.rstrip("/") + "/rest/v1", headers=headers, timeout=30)

    # ---------- helpers ----------
    @staticmethod
    def _check(r: httpx.Response) -> httpx.Response:
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase error {r.status_code}: {r.text[:300]}")
        return r

    def _select_all(self, table: str, params: dict, page: int = 1000) -> list[dict]:
        """PostgREST returns at most ~1000 rows per request: page with the Range header."""
        rows, start = [], 0
        while True:
            r = self._check(self.http.get(f"/{table}", params=params,
                                          headers={"Range-Unit": "items", "Range": f"{start}-{start + page - 1}"}))
            batch = r.json()
            rows.extend(batch)
            if len(batch) < page:
                return rows
            start += page

    # ---------- reads (API) ----------
    def load_units(self) -> list[dict]:
        return self._select_all("units", {"select": "*", "order": "book_key.asc,bab_index.asc,number.asc"})

    def match(self, embedding, madhhab: str, count: int) -> list[dict]:
        r = self._check(self.http.post("/rpc/match_chunks", json={
            "query_embedding": vector_literal(embedding), "filter_madhhab": madhhab, "match_count": count}))
        return r.json()

    def ping(self) -> bool:
        """Cheap query used by /api/health?deep=1 (and the keep-alive job)."""
        self._check(self.http.get("/index_meta", params={"select": "key", "limit": "1"}))
        return True

    # ---------- writes (indexing script) ----------
    def upsert(self, table: str, rows: list[dict], batch: int = 200) -> None:
        for i in range(0, len(rows), batch):
            self._check(self.http.post(f"/{table}", json=rows[i:i + batch],
                                       headers={"Prefer": "resolution=merge-duplicates,return=minimal"}))

    def delete_where(self, table: str, **equals) -> None:
        """DELETE FROM table WHERE col1 = v1 AND ... (at least one filter, to never wipe a table by mistake)."""
        if not equals:
            raise ValueError("delete_where needs at least one filter")
        self._check(self.http.delete(f"/{table}", params={k: f"eq.{v}" for k, v in equals.items()}))

    def get_meta(self, key: str) -> str | None:
        r = self._check(self.http.get("/index_meta", params={"select": "value", "key": f"eq.{key}"}))
        rows = r.json()
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        self.upsert("index_meta", [{"key": key, "value": value}])
