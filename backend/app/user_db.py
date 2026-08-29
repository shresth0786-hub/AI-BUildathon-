"""
USER DATABASE — persisted user / transaction details
-----------------------------------------------------
Stores the **name and other details** of every user whose payment is run
through the live investigation flow (e.g. the "Live fraud check" / a payment
that lands in the review band). Records survive a backend restart because they
are persisted to `backend/database/db/users.json` (gitignored, never on GitHub).

Each record is keyed by `user_id` and keeps the latest values of that user's
most recent investigated payment:
  * identity : user_id, name (payer_name/customer_name if supplied), phone,
               card_last4, device_id
  * context  : merchant, payment_method, amount_inr, attempt_count,
               is_new_device, status
  * outcome  : decision, model scores (ml_risk / behaviour_ai / graph_engine /
               investigator), fraud_vector, and the event_id + timestamp

Why a database file?
  * The RAG pipeline reads it as a first-class **live source**, so an admin can
    ask "who is user X / what did user Y's payment do" and get a grounded answer.
  * The API + dashboard can look up real users and their details instead of
    only aggregate counts.
  * It is intentionally small and human-readable JSON for the demo; in
    production this maps to a real SQL/NoSQL store.
"""

from __future__ import annotations

import json
import os
import threading
import time

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "database", "db")
_USERS_FILE = os.path.join(_DATA_DIR, "users.json")


def _log(msg: str) -> None:
    print(f"[user_db] {msg}")


class UserDatabase:
    def __init__(self, path: str = _USERS_FILE):
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
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, default=str)
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------ write
    def upsert_user(self, user_id: str, event: dict, outcome: dict | None = None,
                    replace: bool = False) -> dict:
        """Persist (or refresh) a user from an investigated payment event and its
        investigation outcome. `replace=False` keeps earlier user fields that a
        later event does not set (e.g. a phone number seen only once)."""
        if not user_id:
            return {}
        with self._lock:
            rec = self._data.get(user_id, {"user_id": user_id})

            def _keep(key, value):
                if value is None:
                    return
                if replace or key not in rec or value:
                    rec[key] = value

            event = event or {}
            _keep("name", event.get("payer_name") or event.get("customer_name") or
                         event.get("name"))
            _keep("phone", event.get("phone") or event.get("payer_phone"))
            _keep("card_last4", event.get("card_last4"))
            _keep("device_id", event.get("device_id"))
            _keep("merchant", event.get("merchant"))
            _keep("payment_method", event.get("payment_method"))
            _keep("amount_inr", event.get("amount_inr"))
            _keep("attempt_count", event.get("attempt_count"))
            _keep("is_new_device", event.get("is_new_device"))
            _keep("status", event.get("status"))

            # outcome
            if outcome:
                rec["decision"] = outcome.get("decision", rec.get("decision"))
                sc = outcome.get("scores") or {}
                if sc:
                    rec["scores"] = sc
                rec["fraud_vector"] = outcome.get("fraud_vector", rec.get("fraud_vector"))
                rec["event_id"] = outcome.get("event_id", rec.get("event_id"))
            rec["updated_at"] = time.time()
            if "first_seen_at" not in rec:
                rec["first_seen_at"] = rec["updated_at"]

            self._data[user_id] = rec
            self._save()
            return rec

    def touch(self, user_id: str, event: dict) -> dict:
        """Record a user whose payment was investigated but keep prior values."""
        return self.upsert_user(user_id, event, None, replace=False)

    # ------------------------------------------------------------------ read
    def all(self) -> list[dict]:
        with self._lock:
            return [self._data[k] for k in
                    sorted(self._data, key=lambda k: self._data[k].get("updated_at", 0),
                           reverse=True)]

    def get(self, user_id: str) -> dict | None:
        with self._lock:
            return self._data.get(user_id)

    def count(self) -> int:
        with self._lock:
            return len(self._data)

    def stats(self) -> dict:
        rows = self.all()
        decisions: dict[str, int] = {}
        for r in rows:
            d = r.get("decision") or "unknown"
            decisions[d] = decisions.get(d, 0) + 1
        return {
            "total_users": len(rows),
            "by_decision": decisions,
            "file": os.path.basename(self._path),
        }


_db: UserDatabase | None = None


def get_user_db() -> UserDatabase:
    global _db
    if _db is None:
        _db = UserDatabase()
    return _db
