"""
RAG ENGINE — ADMIN Q&A (ingests the live dataset)
------------------------------------------------
Lets an admin ask "what is the issue and what should I do about it?" — and also
ask about the REAL, current dataset — and get a grounded, actionable answer.

Two kinds of knowledge are indexed together:

  1. STATIC runbook   (rag_knowledge.py): the curated "issues & remedies" so
     "how do I fix a false-positive surge?" resolves to a procedure.

  2. LIVE dataset      (fed in per request): the system LEARNS from the live
     data by indexing it as searchable chunks:
        * event chunks   : one per recent scored payment (merchant, user, card,
                           amount, decision, model scores, fraud vector) so
                           "why was merchant X blocked?" / "tell me about this
                           user" resolve to the real transaction.
        * insight chunks : aggregates mined from the dataset (top fraud
                           merchants, most-blocked users, top risk cards, fraud
                           rate by decision, review backlog).
        * feedback chunks: confirmed clean/fraud labels + phone-verification
                           verdicts, so the answers reflect what the model has
                           learned from past outcomes.

  3. Generation: the best static and/or live chunks are assembled into a
     structured answer (Issue / Diagnosis / What to do, plus live facts),
     grounded strictly in the corpus — no external LLM, no API key, offline.

The combined index is rebuilt automatically as the live data changes (TTL +
change detection), so the RAG is always looking at the current dataset.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app import rag_knowledge


@dataclass
class RagResult:
    answer: str = ""
    sources: list = field(default_factory=list)
    top: list = field(default_factory=list)


# TTL: rebuild the live part of the index if asked more than this many seconds
# after the last build (live data changes slowly; this keeps asks cheap).
_LIVE_TTL = 20.0


class RAGEngine:
    def __init__(self):
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix: np.ndarray | None = None          # (n_chunks, vocab)
        self._chunks: list[dict] = []
        self._entries: dict = {}
        self._name = None
        # live bookkeeping
        self._live_payload: dict = {}
        self._live_sig: tuple = ()
        self._live_built_at: float = 0.0
        self._n_static = 0
        self._n_live = 0
        self._build_index()

    # ------------------------------------------------------------------ index
    def _build_index(self) -> None:
        self._entries = {e["id"]: e for e in rag_knowledge.KNOWLEDGE}
        self._chunks = rag_knowledge.build_corpus()
        for e in rag_knowledge.KNOWLEDGE:
            words = " ".join(e["tags"]) + " " + e["title"] + " " + e["description"]
            self._chunks.append({"type": "topic", "entry_id": e["id"], "text": words})
        self._n_static = len(self._chunks)
        self._vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
        )
        # static-only matrix (refitted when live chunks are added)
        self._refit()
        self._name = "tfidf-local"

    def _refit(self) -> None:
        texts = [c["text"] for c in self._chunks]
        self._vectorizer.fit(texts)
        self._matrix = self._vectorizer.transform(texts)

    # ---------------------------------------------------------- live indexing
    def _live_chunks(self, live: dict) -> list[dict]:
        """Turn the live dataset payload into searchable chunks (event,
        insight, feedback). This is the 'learn from the dataset' layer."""
        chunks: list[dict] = []

        # ---- event chunks (one per recent scored payment) ----
        indexed_ids = set()

        def _event_chunk(ev: dict) -> dict | None:
            evid = str(ev.get("event_id", ""))
            if not evid or evid in indexed_ids:
                return None
            indexed_ids.add(evid)
            merchants = ev.get("merchant") or "unknown merchant"
            user = ev.get("user_id") or "unknown user"
            decision = ev.get("decision") or "unknown"
            price = ev.get("amount_inr") or 0
            method = ev.get("payment_method") or "card"
            vector = ev.get("fraud_vector") or "none"
            true_label = ev.get("true_label")
            label_word = {0: "legitimate", 1: "fraudulent"}.get(true_label, "unlabelled")
            p_ml = ev.get("p_ml", ev.get("scores", {}).get("ml_risk"))
            p_beh = ev.get("p_behav", ev.get("scores", {}).get("behaviour_ai"))
            p_grf = ev.get("p_graph", ev.get("scores", {}).get("graph_engine"))
            p_inv = ev.get("p_investigator", ev.get("scores", {}).get("investigator"))
            text = (
                f"payment event {evid} merchant {merchants} user {user} "
                f"amount rupees {price} payment method {method} decision {decision} "
                f"fraud vector {vector} labelled {label_word} "
                f"ml risk score {p_ml} behaviour score {p_beh} "
                f"graph score {p_grf} investigator score {p_inv}"
            )
            return {
                "type": "event", "doc_id": f"event:{evid}",
                "text": text, "title": f"event {evid} — {merchants}"
            }

        for ev in (live.get("events") or [])[:150]:
            c = _event_chunk(ev)
            if c:
                chunks.append(c)

        # Live-investigated payments (from the feedback store) are also indexed,
        # so a payment the admin just ran through 'Live fraud check' is queryable.
        for rec in ((live.get("feedback") or {}).get("records") or [])[:100]:
            ev = dict(rec.get("event") or {})
            # the record stores decision + scores separately from the raw event:
            # merge them so the indexed chunk shows the real outcome.
            if "decision" not in ev or ev.get("decision") in (None, "unknown"):
                ev["decision"] = rec.get("decision")
            sc = rec.get("scores") or {}
            if isinstance(sc, dict):
                ev.setdefault("p_ml", sc.get("ml_risk"))
                ev.setdefault("p_behav", sc.get("behaviour_ai"))
                ev.setdefault("p_graph", sc.get("graph_engine"))
                ev.setdefault("p_investigator", sc.get("investigator"))
            c = _event_chunk(ev)
            if c:
                chunks.append(c)

        # ---- insight chunks (aggregates mined from the dataset) ----
        events = live.get("events") or []
        if events:
            def _top(field, bucket, limit=4):
                from collections import Counter
                c = Counter()
                for ev in events:
                    v = ev.get(field)
                    if v is None:
                        continue
                    key = f"{bucket} {v}"
                    c[key] += 1
                return dict(c.most_common(limit))

            top_merchant = _top("merchant", "merchant")
            if top_merchant:
                chunks.append({
                    "type": "insight", "doc_id": "insight:top_merchants",
                    "title": "top merchants by transaction count",
                    "text": "most active merchants " + ", ".join(
                        f"{k} ({v} payments)" for k, v in top_merchant.items()),
                })

            # top risk by decision: block/review counts
            from collections import Counter
            dec = Counter(ev.get("decision") for ev in events)
            chunks.append({
                "type": "insight", "doc_id": "insight:decisions",
                "title": "decision distribution in live data",
                "text": "live decision distribution " + ", ".join(
                    f"{d} {n}" for d, n in dec.items()),
            })

            # fraud rate by vector among true-positives
            vd = Counter()
            vn = Counter()
            for ev in events:
                v = ev.get("fraud_vector") or "none"
                vn[v] += 1
                if ev.get("true_label") == 1:
                    vd[v] += 1
            if vd:
                chunks.append({
                    "type": "insight", "doc_id": "insight:vectors",
                    "title": "fraud vectors in live data",
                    "text": "fraudulent events by vector " + ", ".join(
                        f"{v} ({n}/{vn.get(v, 0)})" for v, n in
                        sorted(vd.items(), key=lambda kv: -kv[1])[:5]),
                })

            # blocked-by-merchant (for 'which merchant has the most fraud')
            if dec.get("block"):
                blocks = Counter(f"{ev.get('merchant')}" for ev in events
                                 if ev.get("decision") == "block")
                if blocks:
                    chunks.append({
                        "type": "insight", "doc_id": "insight:blocked_merchants",
                        "title": "merchants with the most blocked payments",
                        "text": "merchants with blocked payments " + ", ".join(
                            f"{m} ({n} blocked)" for m, n in blocks.most_common(4)),
                    })

        # ---- feedback chunks (what the model has learned) ----
        fb = live.get("feedback") or {}
        for rec in (fb.get("records") or [])[:100]:
            label = rec.get("label")
            if label is None:
                continue
            evid = rec.get("event_id", "")
            src = rec.get("label_source", "manual")
            word = "fraudulent" if label == 1 else "clean"
            chunks.append({
                "type": "feedback", "doc_id": f"feedback:{evid}",
                "title": f"confirmed {word} — {evid}",
                "text": (f"confirmed feedback event {evid} labelled {word} "
                         f"confirmed by source {src}"),
            })

        # ---- verification / phone-call chunks ----
        ver = live.get("verification") or {}
        for s in (ver.get("sessions") or [])[:80]:
            vid = s.get("verification_id", "")
            status = s.get("status", "")
            chunks.append({
                "type": "call", "doc_id": f"call:{vid}",
                "title": f"phone verification {vid} — {status}",
                "text": (f"phone call verification session {vid} status {status} "
                         f"merchant {s.get('merchant') or ''} user "
                         f"{s.get('user_id') or ''} amount rupees "
                         f"{s.get('amount_inr') or 0}"),
            })

        # ---- user database chunks (persisted live-investigated users) ----
        for u in (live.get("users") or [])[:120]:
            uid = u.get("user_id", "")
            if not uid:
                continue
            chunks.append({
                "type": "user", "doc_id": f"user:{uid}",
                "title": f"user {uid}",
                "text": (f"user {uid} name {u.get('name') or 'unknown'} phone "
                         f"{u.get('phone') or 'unknown'} merchant {u.get('merchant') or ''} "
                         f"card last4 {u.get('card_last4') or ''} device "
                         f"{u.get('device_id') or ''} payment method "
                         f"{u.get('payment_method') or ''} amount rupees "
                         f"{u.get('amount_inr') or 0} decision {u.get('decision') or 'unknown'} "
                         f"scores {u.get('scores') or {}}"),
            })

        return chunks

    @staticmethod
    def _compute_signature(live: dict) -> tuple:
        fb = live.get("feedback") or {}
        records = fb.get("records") or []
        ver = live.get("verification") or {}
        sessions = ver.get("sessions") or []
        events = live.get("events") or []
        users = live.get("users") or []
        return (
            len(events),
            len(records),
            len([r for r in records if r.get("label") is not None]),
            len(sessions),
            len(users),
            (events[:1][0].get("event_id") if events else ""),
        )

    def _refresh_live(self, live: dict) -> None:
        if not live:
            return
        sig = self._compute_signature(live)
        now = time.time()
        if self._live_sig == sig and (now - self._live_built_at) < _LIVE_TTL:
            return
        self._live_payload = live
        self._live_sig = sig
        # rebuild = static + fresh live chunks
        self._chunks = rag_knowledge.build_corpus()
        for e in rag_knowledge.KNOWLEDGE:
            words = " ".join(e["tags"]) + " " + e["title"] + " " + e["description"]
            self._chunks.append({"type": "topic", "entry_id": e["id"], "text": words})
        live_chunks = self._live_chunks(live)
        self._chunks.extend(live_chunks)
        self._n_live = len(live_chunks)
        self._n_static = len(self._chunks) - self._n_live
        self._refit()
        self._live_built_at = now

    # ------------------------------------------------------------------ query
    def _rank(self, question: str, k: int = 6):
        q_vec = self._vectorizer.transform([question])
        scores = np.asarray((self._matrix @ q_vec.T).toarray()).ravel()
        order = np.argsort(-scores)
        top = []
        seen = set()
        for idx in order:
            ch = self._chunks[idx]
            s = float(scores[idx])
            if s <= 0:
                continue
            key = ch.get("doc_id") or ch.get("entry_id")
            if key in seen:
                continue
            seen.add(key)
            top.append((key, round(s, 3), ch))
            if len(top) >= k:
                break
        return top

    def _match_static(self, question: str) -> list[str]:
        q = question.lower()
        static = []
        if any(w in q for w in ["chargeback", "false negative", "fraud approved",
                                "leak", "got approved"]):
            static.append("false_negatives")
        if any(w in q for w in ["false positive", "legit", "legitimate", "blocked",
                                "clean", "friction"]):
            static.append("false_positive_surge")
        if any(w in q for w in ["retrain", "retrain", "learning", "feedback"]):
            static.append("model_retrain")
        if any(w in q for w in ["twilio", "call", "phone", "recording"]):
            static.append("twilio_real_calls")
        return [e for e in static if e in self._entries]

    # ------------------------------------------------------------------ ask
    def ask(self, question: str, live: dict | None = None) -> RagResult:
        if not question or not question.strip():
            return RagResult(answer="Please ask a question about a fraud issue.")
        self._refresh_live(live or {})
        top = self._rank(question, k=6)

        # split hits into static (runbook) vs live (dataset) chunks
        runbook_hits = [t for t in top if t[2].get("entry_id")]
        live_hits = [t for t in top if t[2].get("type") in ("event", "insight", "feedback", "call", "user")]

        # static keyword fallback (dedupe with runbook hits)
        hit_rids = {t[0] for t in runbook_hits}
        for eid in self._match_static(question):
            if eid in self._entries and eid not in hit_rids:
                runbook_hits.insert(0, (eid, 0.0, {"entry_id": eid}))

        lines: list[str] = []
        sources: list[dict] = []

        # --- answer from LIVE data when a real transaction/insight matches ---
        if live_hits:
            if any(h[2]["type"] == "event" for h in live_hits):
                lines.append("FOUND IN LIVE DATA")
                for _, sc, ch in live_hits[:3]:
                    lines.append(f"• {ch['title']} — {ch['text']}")
            elif any(h[2]["type"] == "insight" for h in live_hits):
                lines.append("LIVE DATASET")
                for _, sc, ch in live_hits[:3]:
                    lines.append(f"• {ch['title']}: {ch['text']}")
            else:
                lines.append("LEARNED / VERIFIED")
                for _, sc, ch in live_hits[:3]:
                    lines.append(f"• {ch['title']} — {ch['text']}")
            for _, sc, ch in live_hits[:3]:
                sources.append({
                    "id": ch.get("doc_id") or ".", "title": ch.get("title", ""),
                    "severity": "live-"+ch["type"], "score": sc,
                })
            lines.append("")

        # --- runbook guidance ---
        if runbook_hits:
            best_eid = runbook_hits[0][0]
            best = self._entries.get(best_eid)
            if best:
                lines += [
                    f"#{best['id']} — {best['title']}",
                    f"Severity: {best['severity']}",
                    "",
                    "WHAT TO DO",
                    best["remedy"],
                ]
                sources.insert(0, {
                    "id": best["id"], "title": best["title"],
                    "severity": best["severity"], "score": runbook_hits[0][1],
                })

        if not live_hits and not runbook_hits:
            return RagResult(answer=(
                "I don't have a specific runbook for that question. Try asking "
                "about a merchant, user or event that appears in the payment "
                "stream, or about: false positives, false negatives, card "
                "testing, account takeover, review backlog, retraining, Twilio, "
                "Razorpay keys, decision thresholds, or the test metrics."
            ))

        # --- always append CURRENT STATE (live numbers) ---
        ls = (live or {}).get("test") or {}
        fb = (live or {}).get("feedback") or {}
        fbstore = fb.get("store") or {}
        ver = (live or {}).get("verification") or {}
        vs = ver.get("status") or {}
        parts = ["CURRENT STATE"]
        if ls:
            parts.append(
                f"  held-out test: {ls.get('false_positives')} false positives, "
                f"{ls.get('false_negatives')} false negatives, "
                f"{ls.get('recall_fraud_blocked')} recall."
            )
        parts.append(
            f"  continual learning: {fbstore.get('labelled', 0)} labelled / "
            f"{fbstore.get('total_recorded', 0)} recorded, "
            f"{((fb.get('corrector') or {}).get('updates', 0))} online updates."
        )
        parts.append(
            f"  phone verification: {vs.get('active', 0)} active sessions, "
            f"mode={vs.get('mode')}."
        )
        lines.extend(parts)

        # related runbook topics
        related = [rid for (rid, _, ch) in runbook_hits[1:]]
        for rid in related:
            e = self._entries.get(rid)
            if e:
                lines.append("")
                lines.append(f"Related: {e['id']} — {e['title']}")

        result = RagResult()
        result.answer = "\n".join(lines)
        result.sources = sources
        result.top = [
            {"id": t[0], "title": t[2].get("title") or t[2].get("entry_id"),
             "score": t[1], "type": t[2].get("type", "runbook")} for t in top
        ]
        return result

    def knowledge(self) -> list[dict]:
        return [
            {"id": e["id"], "title": e["title"], "severity": e["severity"],
             "tags": e["tags"], "questions": e["questions"]}
            for e in rag_knowledge.KNOWLEDGE
        ]

    def status(self) -> dict:
        return {
            "engine": self._name,
            "entries": len(self._entries),
            "chunks_total": len(self._chunks),
            "runbook_chunks": self._n_static,
            "live_chunks": self._n_live,
            "offline": True,
            "learns_from_live_data": True,
        }


_engine: RAGEngine | None = None


def get_rag() -> RAGEngine:
    global _engine
    if _engine is None:
        _engine = RAGEngine()
    return _engine
