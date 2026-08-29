"""
SENTINEL AI — customer-care QUERY database
------------------------------------------
A **separate** persistence store for the queries that customers / partners raise
to customer care. Deliberately isolated from:
  * the user database  (`database/db/users.json`)  — investigated-payment user details
  * the payment datasets (training/event data)     — model/transaction rows

Why a separate file?
  * A query is a support interaction, not a payment or a user identity. Mixing
    them would let support tickets contaminate the fraud/RAG live dataset.
  * The RAG/admin surfaces read the user database; customer-care queries live in
    their own file so one team's data never leaks into another's view.
  * Persisted to `backend/database/db/queries.json` (gitignored, never on GitHub).

Each record:
  * query_id, author (customer name/contact), category, message
  * status  : new -> in_progress -> resolved
  * created_at, updated_at, assigned_to, resolution (admin/care note)
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "database", "db")
_QUERIES_FILE = os.path.join(_DB_DIR, "queries.json")

VALID_STATUS = {"new", "in_progress", "resolved"}
VALID_CATEGORIES = {
    "payment", "refund", "account", "fraud_report", "verification", "other",
}


def _log(msg: str) -> None:
    print(f"[query_db] {msg}")


class QueryDatabase:
    def __init__(self, path: str = _QUERIES_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                self._data = raw
        except Exception as exc:  # pragma: no cover
            _log(f"failed to load {self._path}: {exc}")

    def _save(self) -> None:
        os.makedirs(_DB_DIR, exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, default=str)
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------ write
    def create_query(self, author: str, message: str, category: str = "other",
                     contact: str = "") -> dict:
        """Open a new support ticket in the query database."""
        category = category if category in VALID_CATEGORIES else "other"
        query_id = "qry_" + uuid.uuid4().hex[:12]
        now = time.time()
        rec = {
            "query_id": query_id,
            "author": (author or "unknown").strip() or "unknown",
            "category": category,
            "message": (message or "").strip(),
            "contact": contact or "",
            "status": "new",
            "assigned_to": "",
            "resolution": "",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._data[query_id] = rec
            self._save()
        return rec

    def update_query(self, query_id: str, *, status: str | None = None,
                     assigned_to: str | None = None,
                     resolution: str | None = None) -> dict | None:
        with self._lock:
            rec = self._data.get(query_id)
            if rec is None:
                return None
            if status is not None:
                if status not in VALID_STATUS:
                    raise ValueError(f"invalid status: {status}")
                rec["status"] = status
            if assigned_to is not None:
                rec["assigned_to"] = assigned_to
            if resolution is not None:
                rec["resolution"] = resolution
            rec["updated_at"] = time.time()
            self._save()
            return rec

    # ------------------------------------------------------------------ read
    def all(self) -> list[dict]:
        with self._lock:
            return sorted(
                [self._data[k] for k in self._data],
                key=lambda r: r.get("created_at", 0), reverse=True,
            )

    def get(self, query_id: str) -> dict | None:
        with self._lock:
            return self._data.get(query_id)

    def stats(self) -> dict:
        rows = self.all()
        by_status: dict[str, int] = {}
        for r in rows:
            s = r.get("status") or "new"
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_queries": len(rows),
            "by_status": by_status,
            "file": os.path.basename(self._path),
        }


_db: QueryDatabase | None = None


def get_query_db() -> QueryDatabase:
    global _db
    if _db is None:
        _db = QueryDatabase()
    return _db
