"""
FastAPI service that hosts the fraud-detection stack and serves the dashboard.

Run from backend/:

    uvicorn app.main:app --reload --port 8000

Endpoints
---------
GET  /api/health
GET  /api/summary            -> model / data summary + decision metrics
GET  /api/events?limit=&risk= -> recent payment events with scores & decisions
GET  /api/events/{event_id}  -> full investigation report for one event
POST /api/investigate        -> run the live pipeline on a JSON payment event
GET  /api/vectors            -> fraud-vector distribution
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.pipeline import FraudDetector
from app import razorpay_client
from app.verification import verifier

_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts")

app = FastAPI(title="Razorpay Fraud Guardian API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_detector: FraudDetector | None = None


def get_detector() -> FraudDetector:
    global _detector
    if _detector is None:
        _detector = FraudDetector.load()
    return _detector


# ------------------------------------------------------------------ pydantic
class PaymentEvent(BaseModel):
    user_id: str = Field(..., description="payer identifier")
    device_id: str = Field("", description="device fingerprint")
    card_last4: str = Field("0000", description="last 4 digits of the card")
    amount_inr: float = Field(..., gt=0)
    merchant: str = "Unknown Store"
    payment_method: str = "card"
    card_bin_country: str = "IN"
    ip_geo_match: bool = True
    is_international: bool = False
    billing_zip: str = "400001"
    shipping_zip: str = "400001"
    typing_seconds: float = 15.0
    attempt_count: int = 1
    is_new_device: bool = False
    three_ds_passed: bool = True
    status: str = "captured"
    phone: str = ""


class InvestigateRequest(BaseModel):
    event: PaymentEvent
    history: list[PaymentEvent] = Field(
        default_factory=list,
        description="optional prior payments from the same entity that supply "
                    "velocity/behaviour context (card-testing / burst demo)",
    )


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "razorpay-fraud-guardian"}


@app.get("/api/summary")
def summary():
    det = get_detector()
    return {
        **det.summary,
        "decision_metrics": det.decision_metrics(),
        "model_weights": det.summary.get("weights"),
    }


@app.get("/api/test-metrics")
def test_metrics():
    """Honest held-out test-set metrics: precision/recall/F1 + false-positive cost."""
    det = get_detector()
    return det.test_metrics()


@app.get("/api/events")
def events(limit: int = Query(200, le=2000),
           risk: Optional[str] = Query(None, pattern="^(approve|review|block)$")):
    det = get_detector()
    dec = det.decisions()
    if risk:
        dec = dec[dec["decision"] == risk]
    dec = dec.sort_values("p_investigator", ascending=False).head(limit)
    cols = ["event_id", "user_id", "merchant", "amount_inr", "payment_method",
            "status", "p_ml", "p_behav", "p_graph", "p_investigator",
            "decision", "true_label", "fraud_vector"]
    return dec[cols].to_dict(orient="records")


@app.get("/api/events/{event_id}")
def event_detail(event_id: str):
    det = get_detector()
    match = det.event_df.index[det.event_df["event_id"] == event_id]
    if len(match) == 0:
        raise HTTPException(404, "event not found")
    idx = int(match[0])
    row = det.event_df.iloc[idx]
    out = det.investigator.investigate(
        idx,
        float(row["p_ml"]),
        float(row["p_behav"]),
        float(row["p_graph"]),
    )
    return out


@app.get("/api/vectors")
def vectors():
    det = get_detector()
    v = det.event_df[det.event_df["fraud_vector"].notna()]
    counts = v["fraud_vector"].value_counts().to_dict()
    return {"vectors": counts, "total_fraud": int(v.shape[0])}


@app.post("/api/investigate")
def investigate(req: InvestigateRequest):
    det = get_detector()
    evt = req.event.model_dump()
    history = [h.model_dump() for h in req.history]
    try:
        return det.investigate_event(evt, history=history)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"investigation failed: {exc}") from exc


# ---------------------------------------------------------------- verification
class OtpRequest(BaseModel):
    otp: str = Field(..., min_length=1, max_length=12,
                     description="one-time passcode the payer read back over the phone")


class VerifyEventRequest(BaseModel):
    event: PaymentEvent


@app.get("/api/verification")
def verification_list():
    """All phone-call payment-confirmation sessions (active + resolved)."""
    return {"sessions": verifier().list(), "status": verifier().status()}


@app.get("/api/verification/{verification_id}")
def verification_get(verification_id: str):
    try:
        return verifier().get(verification_id)
    except KeyError:
        raise HTTPException(404, "verification not found")


@app.post("/api/verification/{verification_id}/confirm")
def verification_confirm(verification_id: str, body: OtpRequest):
    """Complete the phone call. Correct OTP -> APPROVE. Wrong OTP / cap exceeded
    -> escalate to BLOCK. The payer's ownership confirmation is implicit via the
    call script."""
    try:
        return verifier().confirm(verification_id, body.otp)
    except KeyError:
        raise HTTPException(404, "verification not found")


@app.post("/api/verification/{verification_id}/deny")
def verification_deny(verification_id: str):
    """The payer denied making this payment -> escalate to BLOCK."""
    try:
        return verifier().deny(verification_id)
    except KeyError:
        raise HTTPException(404, "verification not found")


@app.post("/api/verification/{verification_id}/resend")
def verification_resend(verification_id: str):
    """Regenerate the OTP and re-place the call."""
    try:
        return verifier().resend(verification_id)
    except KeyError:
        raise HTTPException(404, "verification not found")


@app.post("/api/verify/event")
def verify_event(req: VerifyEventRequest):
    """Score an event and, if it lands on the medium-risk band, return a live
    phone-verification handle ready for OTP confirmation."""
    det = get_detector()
    evt = req.event.model_dump()
    try:
        res = det.investigate_event(evt)
        return res
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"verification setup failed: {exc}") from exc


# ------------------------------------------------------------------ RAG / admin Q&A
class RagRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


@app.get("/api/rag/status")
def rag_status():
    from app.rag import get_rag
    return get_rag().status()


@app.get("/api/rag/knowledge")
def rag_knowledge():
    from app.rag import get_rag
    return {"issues": get_rag().knowledge()}


@app.post("/api/rag/ask")
def rag_ask(req: RagRequest):
    """Admin Q&A: 'what is the issue and what should I do about it?'. Retrieves
    the best-matching known-issue runbook and grounds the answer with LIVE state
    (test metrics, continual-learning status, pending verifications)."""
    from app.rag import get_rag
    det = get_detector()
    live = {"test": det.test_metrics()}
    try:
        from app.feedback import get_controller
        live["feedback"] = get_controller().status()
    except Exception:  # pragma: no cover
        live["feedback"] = {}
    try:
        from app.verification import verifier
        live["verification"] = {"status": verifier().status()}
    except Exception:  # pragma: no cover
        live["verification"] = {}
    res = get_rag().ask(req.question, live=live)
    return {
        "question": req.question,
        "answer": res.answer,
        "sources": res.sources,
        "top": res.top,
    }


# ---------------------------------------------------------------- continual learning
class CorrectRequest(BaseModel):
    is_fraud: bool = Field(..., description="true verdict for this transaction")


@app.get("/api/feedback")
def feedback_list():
    """Continual-learning status plus the labelled (and unlabelled) transaction log."""
    from app.feedback import get_controller
    c = get_controller()
    return {"status": c.status(), "records": c.records()}


@app.post("/api/feedback/{event_id}/correct")
def feedback_correct(event_id: str, body: CorrectRequest):
    """Manually correct the decision for a previously scored transaction.
    Feeds the online corrector immediately and queues it for the next retrain."""
    from app.feedback import get_controller
    c = get_controller()
    rec = c.store.get(event_id)
    if rec is None:
        raise HTTPException(404, "transaction not found (run /api/investigate first)")
    ok = c.label(event_id, 1 if body.is_fraud else 0, "manual", corrected=True)
    return {"ok": bool(ok), "label": 1 if body.is_fraud else 0,
            "status": c.status(), "record": c.store.get(event_id)}


@app.post("/api/learning/retrain")
def learning_retrain(seed: int = Query(42)):
    """Retrain the supervised models (ML Risk + Investigator) on the original
    synthetic data PLUS all confirmed feedback, then hot-swap the live model."""
    global _detector
    from app.feedback import get_controller
    from app.pipeline import FraudDetector
    c = get_controller()
    labelled = c.store.labelled()
    fresh = FraudDetector.load()
    try:
        summary = fresh.retrain_with_feedback(labelled, seed=seed)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"retrain failed: {exc}") from exc
    _detector = fresh
    return {"ok": True, "feedback_used": summary.get("feedback_used", 0),
            "investigator_auc": summary.get("investigator_auc"),
            "ml_auc": summary.get("ml_auc"),
            "test": summary.get("test")}


# ------------------------------------------------------------------ razorpay
@app.get("/api/rzp/status")
def rzp_status():
    return {
        "configured": razorpay_client.is_configured(),
        "live": os.getenv("RAZORPAY_KEY_ID", "").startswith("rzp_live"),
        "message": (
            "Real test-mode keys detected. Create an order and send webhooks "
            "to /api/rzp/webhook."
            if razorpay_client.is_configured()
            else ("Live keys detected - never use these in a demo. Use rzp_test_ keys only."
                  if os.getenv("RAZORPAY_KEY_ID", "").startswith("rzp_live")
                  else "Not configured. Set RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET (rzp_test_) in backend/.env to enable real test-mode integration.")
        ),
    }


@app.post("/api/rzp/create-order")
def rzp_create_order(amount_inr: float = Query(100.0, gt=0)):
    """Create a real Razorpay TEST order (requires rzp_test_ keys)."""
    try:
        order = razorpay_client.create_test_order(amount_inr)
        return {"ok": True, "order": order}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/rzp/webhook")
def rzp_webhook(payload: dict):
    """Ingest a real Razorpay 'payment.captured' (or 'order.paid') webhook and
    run it through the fraud pipeline, returning live decision + evidence."""
    event_name = payload.get("event", "")
    if "payment.captured" not in event_name and "order.paid" not in event_name:
        raise HTTPException(400, f"unsupported event: {event_name}")
    try:
        evt = razorpay_client.webhook_event_to_payload(payload)
        return get_detector().investigate_event(evt)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"webhook ingestion failed: {exc}") from exc


@app.get("/api/rzp/demo-payment")
def rzp_demo_payment():
    """A ready-made 'card testing' demo batch for POST /api/investigate
    (see module docstring)."""
    return razorpay_client.demo_payment_for_testing()


@app.get("/api/demo/fraud")
def demo_fraud():
    """Fraud demo: card-testing burst body for POST /api/investigate."""
    return razorpay_client.demo_payment_for_testing()


@app.get("/api/demo/clean")
def demo_clean():
    """Clean demo: benign established-customer payment body for /api/investigate."""
    return {"event": razorpay_client.demo_clean_payment(), "history": []}
