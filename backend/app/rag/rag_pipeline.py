"""
RAG PIPELINE — connects the user database + live sources to the RAG engine
----------------------------------------------------------------------------
This is the orchestration layer ("pipeline") that ties the whole Admin Q&A flow
together:

    user database  ─┐
    data.metrics    ─┤
    feedback store  ─┼─►  build_live_context()  ─►  RAGEngine.ask()  ─►  answer
    verification    ─┤                                  │
    live events     ─┘                                  ▼
                                              POST /api/rag/ask (frontend)

It gathers EVERY live source into one context dict, hands it to the local TF-IDF
RAG engine (which indexes the dataset as searchable chunks), and returns a
structured, grounded answer for the admin dashboard.

Keeping this in its own file means the frontend/backend/DB responsibilities are
separate:
  * backend/app/rag/rag_pipeline.py   -> orchestration (this file)
  * backend/app/rag/rag.py            -> retrieval + generation
  * backend/app/rag/rag_knowledge.py  -> static runbook
  * backend/app/database/user_db.py   -> persisted user details (the DB file)
  * backend/app/database/query_db.py  -> admin customer-care queries
  * frontend component                -> AdminRagPanel
"""

from __future__ import annotations

from typing import Any


def gather_user_records() -> list[dict]:
    """Pull the persisted user database records into the live context."""
    try:
        from app.database import get_user_db
        return get_user_db().all()
    except Exception:  # pragma: no cover
        return []


def gather_events(det) -> list[dict]:
    """Top-risk scored events from the detector's dataset."""
    try:
        dec = det.decisions().sort_values("p_investigator", ascending=False)
        cols = ["event_id", "user_id", "merchant", "amount_inr", "payment_method",
                "status", "p_ml", "p_behav", "p_graph", "p_investigator",
                "decision", "true_label", "fraud_vector"]
        return dec[cols].head(150).to_dict(orient="records")
    except Exception:  # pragma: no cover
        return []


def gather_feedback() -> dict:
    try:
        from app.feedback import get_controller
        c = get_controller()
        return {**c.status(), "records": c.records()}
    except Exception:  # pragma: no cover
        return {}


def gather_verification() -> dict:
    try:
        from app.verification import verifier
        return {"status": verifier().status(), "sessions": verifier().list()}
    except Exception:  # pragma: no cover
        return {}


def build_live_context(det) -> dict:
    """Assemble every live source the RAG needs, including the user DB."""
    live: dict[str, Any] = {
        "test": det.test_metrics(),
        "events": gather_events(det),
        "users": gather_user_records(),
        "feedback": gather_feedback(),
        "verification": gather_verification(),
        "meta": {
            "pipeline": "rag_pipeline",
            "sources": ["user_db", "events", "feedback", "verification", "metrics"],
        },
    }
    return live


def ask_admin(question: str, det=None):
    """End-to-end: live context -> RAG engine -> grounded answer."""
    from app.rag.rag import get_rag
    if det is None:
        from app.main import get_detector
        det = get_detector()
    context = build_live_context(det)
    res = get_rag().ask(question, live=context)
    return {
        "question": question,
        "answer": res.answer,
        "sources": res.sources,
        "top": res.top,
        "context": {
            "users": len(context.get("users") or []),
            "events": len(context.get("events") or []),
            "records": len((context.get("feedback") or {}).get("records") or []),
            "sessions": len((context.get("verification") or {}).get("sessions") or []),
        },
    }


def pipeline_status() -> dict:
    det = None
    try:
        from app.main import get_detector
        det = get_detector()
    except Exception:  # pragma: no cover
        pass
    ctx = build_live_context(det) if det else {}
    from app.rag.rag import get_rag
    st = get_rag().status()
    return {
        **st,
        "pipeline": "rag_pipeline",
        "sources": {
            "user_db": len(ctx.get("users") or []),
            "events": len(ctx.get("events") or []),
            "feedback_records": len((ctx.get("feedback") or {}).get("records") or []),
            "verification_sessions": len((ctx.get("verification") or {}).get("sessions") or []),
        },
    }
