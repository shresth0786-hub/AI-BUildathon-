"""
RAG ENGINE — ADMIN Q&A
----------------------
Lets an admin ask "what is the issue and what should I do about it?" and get a
grounded, actionable answer specific to THIS system.

Approach (offline, dependency-light):
  * Retrieval : TF-IDF (sklearn TfidfVectorizer) + cosine similarity over a
                curated knowledge base (see rag_knowledge.py). Each natural-
                language question phrase, title and tag is a searchable chunk,
                so an arbitrary admin question maps to the right issue entry.
  * Generation: the best-matching entries are assembled into a structured
                answer (Issue / Diagnosis / What to do), grounded strictly in
                the knowledge base -- no external LLM, no API key, works fully
                offline. We additionally attach LIVE state (false positives /
                false negatives / pending verifications) so "is there a problem
                right now?" returns current numbers.

The index is built once and cached; `ask()` is called per query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app import rag_knowledge


@dataclass
class RagResult:
    answer: str = ""
    sources: list = field(default_factory=list)
    top: list = field(default_factory=list)


class RAGEngine:
    def __init__(self):
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix: np.ndarray | None = None          # (n_chunks, vocab)
        self._chunks: list[dict] = []
        self._entries: dict = {}
        self._name = None
        self._build_index()

    # ------------------------------------------------------------------ index
    def _build_index(self) -> None:
        self._entries = {e["id"]: e for e in rag_knowledge.KNOWLEDGE}
        self._chunks = rag_knowledge.build_corpus()

        # Add titles + a searchable "all signal words" chunk per entry so an
        # admin typing a symptom (e.g. "chargeback") still matches.
        for e in rag_knowledge.KNOWLEDGE:
            words = " ".join(e["tags"]) + " " + e["title"] + " " + e["description"]
            self._chunks.append({"type": "topic", "entry_id": e["id"], "text": words})

        texts = [c["text"] for c in self._chunks]
        self._vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(texts)
        self._name = "tfidf-local"

    # ------------------------------------------------------------------ query
    def _rank(self, question: str, k: int = 4):
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
            if ch["entry_id"] in seen:
                continue
            seen.add(ch["entry_id"])
            top.append((ch["entry_id"], round(s, 3), ch["text"]))
            if len(top) >= k:
                break
        return top

    def _match_static(self, question: str) -> list[str]:
        """Keyword fallbacks for very common admin questions where semantics
        matter more than TF-IDF phrasing."""
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
        top = self._rank(question, k=5)
        # merge static keyword hits (dedupe)
        ids = [t[0] for t in top]
        for eid in self._match_static(question):
            if eid not in ids:
                # re-rank to front
                ids.insert(0, eid)

        result = RagResult()
        used = [eid for eid in ids if eid in self._entries]
        if not used:
            result.answer = (
                "I don't have a specific runbook for that question. Try asking "
                "about: false positives, false negatives, card testing, account "
                "takeover, review backlog, retraining, Twilio phone calls, "
                "Razorpay keys, decision thresholds, or the test metrics."
            )
            return result

        best = self._entries[used[0]]
        lines = [
            f"#{best['id']} — {best['title']}",
            f"Severity: {best['severity']}",
            "",
            "ISSUE",
            best["description"],
            "",
            "DIAGNOSIS",
            best["diagnosis"],
            "",
            "WHAT TO DO",
            best["remedy"],
        ]

        # live state appended so the admin sees current numbers as context
        if live:
            ls = live.get("test") or {}
            fb = live.get("feedback") or {}
            ver = live.get("verification") or {}
            parts = ["CURRENT STATE"]
            if ls:
                parts.append(
                    f"  held-out test: {ls.get('false_positives')} false positives, "
                    f"{ls.get('false_negatives')} false negatives, "
                    f"{ls.get('recall_fraud_blocked')} recall."
                )
            fbstore = fb.get("store") or {}
            parts.append(
                f"  continual learning: {fbstore.get('labelled', 0)} labelled / "
                f"{fbstore.get('total_recorded', 0)} recorded, "
                f"{((fb.get('corrector') or {}).get('updates', 0))} online updates."
            )
            vs = ver.get("status") or {}
            parts.append(f"  phone verification: {vs.get('active', 0)} active sessions, mode={vs.get('mode')}.")
            lines.append(("").join("\n"))
            lines.append("\n".join(parts))

        # related
        for eid in used[1:]:
            lines.append("")
            lines.append(f"Related: {self._entries[eid]['id']} — {self._entries[eid]['title']}")

        result.answer = "\n".join(lines)
        score_map = {t[0]: t[1] for t in top}
        result.sources = [
            {
                "id": eid, "title": self._entries[eid]["title"],
                "severity": self._entries[eid]["severity"],
                "score": score_map.get(eid, 0.0),
            } for eid in used
        ]
        result.top = [{"id": eid, "title": self._entries[eid]["title"],
                       "score": score_map.get(eid)} for eid in used]
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
            "chunks": len(self._chunks),
            "offline": True,
        }


_engine: RAGEngine | None = None


def get_rag() -> RAGEngine:
    global _engine
    if _engine is None:
        _engine = RAGEngine()
    return _engine
