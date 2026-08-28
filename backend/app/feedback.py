"""
FEEDBACK / CONTINUAL LEARNING
-----------------------------
Gives the fraud model a mechanism to LEARN from each transaction so it does not
repeat the same decision error again and again.

Two complementary mechanisms (as requested):

  1. ONLINE CORRECTION LAYER
     A lightweight online logistic maps the investigator's ensemble score to a
     corrected fraud probability. Every *confirmed* outcome (human verdict,
     OTP confirm/deny, manual operator correction) is fed to an online SGD
     update so the decision boundary adapts immediately -- before a full
     retrain is warranted. This is the "fast" path.

  2. PERIODIC / ON-DEMAND RETRAIN
     All confirmed feedback accumulates in a labelled log. On demand (or after
     enough confirmed corrections) the supervised models (ML Risk + the
     Investigator ensemble) are retrained on the original synthetic data PLUS
     the confirmed feedback, and the artifacts are re-persisted. This is the
     "thorough" path that fixes root causes, not just the top layer.

Ground-truth sources (called 'labels'):
  * otp_confirm  -> payer confirmed ownership -> clean (label 0)
  * otp_deny     -> payer denied ownership   -> fraud (label 1)
  * manual       -> an operator marks a decision correct/incorrect
  * chargeback   -> reserved for a later real chargeback webhook

Every scored transaction is recorded (unlabelled) so it can be labelled later,
meaning the model can learn from decisions it did NOT make (false positives /
false negatives), not only from the review band.
"""

from __future__ import annotations

import json
import os
import threading
import time

import numpy as np

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_FEEDBACK_FILE = os.path.join(_DATA_DIR, "feedback.json")

# ---- sink to allow the dialog to be monkey-patched away in tests ----
def _log(msg: str) -> None:
    print(f"[feedback] {msg}")


class FeedbackStore:
    """Append-only (by event) JSON log of scored transactions + their labels."""

    def __init__(self, path: str = _FEEDBACK_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._data = raw
        except (FileNotFoundError, ValueError, OSError):
            self._data = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:  # pragma: no cover - persistence is best-effort
            pass

    # ------------------------------------------------------------------ writes
    def record(self, event_id: str, event: dict, features: dict,
               scores: dict, decision: str, corrected_prob: float) -> dict:
        """Register a scored transaction (idempotent by event_id). Existing
        record keeps its label; we refresh the latest scores/decision."""
        with self._lock:
            rec = self._data.get(event_id, {})
            prev_label = rec.get("label")
            prev_source = rec.get("label_source")
            rec.update({
                "event_id": event_id,
                "event": event,
                "features": features,
                "scores": scores,
                "decision": decision,
                "p_corrected": round(float(corrected_prob), 4),
                "created_at": rec.get("created_at", time.time()),
                "label": prev_label,
                "label_source": prev_source,
            })
            self._data[event_id] = rec
            self._save()
            return rec

    def label(self, event_id: str, label: int, source: str,
              corrected: bool = False) -> dict | None:
        """Attach a confirmed label to a previously recorded transaction."""
        with self._lock:
            rec = self._data.get(event_id)
            if rec is None:
                return None
            rec["label"] = int(label)
            rec["label_source"] = source
            rec["corrected"] = bool(corrected)
            rec["labelled_at"] = time.time()
            self._data[event_id] = rec
            self._save()
            return rec

    # ------------------------------------------------------------------ reads
    def get(self, event_id: str) -> dict | None:
        return self._data.get(event_id)

    def all(self) -> list[dict]:
        return [self._data[k] for k in
                sorted(self._data, key=lambda k: self._data[k].get("created_at", 0))]

    def labelled(self) -> list[dict]:
        return [r for r in self.all() if r.get("label") is not None]

    def unlabelled(self) -> list[dict]:
        return [r for r in self.all() if r.get("label") is None]

    def status(self) -> dict:
        lab = self.labelled()
        by_src: dict[str, int] = {}
        for r in lab:
            by_src[r.get("label_source") or "unknown"] = by_src.get(
                r.get("label_source") or "unknown", 0) + 1
        return {
            "total_recorded": len(self._data),
            "labelled": len(lab),
            "unlabelled": len(self.unlabelled()),
            "by_source": by_src,
            "corrected_manual": sum(1 for r in lab if r.get("corrected")),
        }


class OnlineCorrector:
    """An online logistic that re-weights the investigator's score using
    confirmed feedback. Uses `SGDClassifier(partial_fit)` on the logit of the
    ensemble probability with only the confirmed-feedback stream, so the
    boundary adapts immediately without retraining the base models."""

    def __init__(self, lr: float = 0.05, epochs_per_point: int = 3):
        from sklearn.linear_model import SGDClassifier
        self._clf = SGDClassifier(
            loss="log_loss", learning_rate="constant", eta0=lr,
            max_iter=epochs_per_point, shuffle=False, random_state=1)
        self._initialised = False
        self._n_updates = 0

    def _logit(self, p: float) -> float:
        p = float(np.clip(p, 1e-6, 1.0 - 1e-6))
        return float(np.log(p / (1.0 - p)))

    def _ensure_init(self, z: float, y: int) -> None:
        if not self._initialised:
            # prime classes so partial_fit can label new batches
            self._clf.partial_fit(np.array([[z]], dtype=np.float64),
                                  np.array([y]), classes=np.array([0, 1]))
            self._initialised = True

    def update(self, p_investigator: float, label: int) -> None:
        """Feed one confirmed outcome: real p + true label."""
        z = self._logit(float(p_investigator))
        self._ensure_init(z, int(label))
        # one pass over this single point (partial_fit accumulates)
        self._clf.partial_fit(np.array([[z]], dtype=np.float64),
                              np.array([int(label)]))
        self._n_updates += 1

    def adjust(self, p_investigator: float) -> float:
        """Map the raw investigator probability through the learned boundary."""
        if not self._initialised or self._n_updates == 0:
            return float(p_investigator)
        z = self._logit(float(p_investigator))
        try:
            pred = float(self._clf.predict_proba(
                np.array([[z]], dtype=np.float64))[0, 1])
        except Exception:  # pragma: no cover - fall back to raw on any failure
            return float(p_investigator)
        # blend gently toward the corrected probability so a couple of labels
        # can't radically flip a well-calibrated ensemble
        alpha = min(1.0, 0.3 + 0.7 * (self._n_updates / 50.0))
        return float(alpha * pred + (1 - alpha) * p_investigator)

    def stats(self) -> dict:
        return {"updates": self._n_updates}


class LearningController:
    """Coordinates the store, the online corrector and periodic retrain."""

    def __init__(self, store: FeedbackStore | None = None,
                 corrector: OnlineCorrector | None = None):
        self.store = store or FeedbackStore()
        self.corrector = corrector or OnlineCorrector()
        self._retrain_lock = threading.Lock()

    # ------------------------------------------------------------------ record
    def record(self, event_id: str, event: dict, features: dict,
               scores: dict, decision: str, p_corrected: float) -> None:
        self.store.record(event_id, event, features, scores, decision, p_corrected)

    def label(self, event_id: str, label: int, source: str,
              p_used: float | None = None, corrected: bool = False) -> bool:
        """Confirm a label for a transaction. Also feeds the online corrector
        on the score that was used to decide (so it learns from the error)."""
        rec = self.store.get(event_id)
        p = p_used
        if rec is not None and p is None:
            p = rec.get("p_corrected") or rec.get("scores", {}).get("investigator")
        stored = self.store.label(event_id, label, source, corrected=corrected)
        if stored is not None and p is not None:
            self.corrector.update(p, label)
            _log(f"labeled {event_id} -> fraud={label} via {source} (p={p:.3f})")
        return stored is not None

    # ------------------------------------------------------------------ query
    def status(self) -> dict:
        return {"store": self.store.status(), "corrector": self.corrector.stats()}

    def records(self) -> list[dict]:
        return self.store.all()


# ------------------------------------------------------------------ singleton
_controller: LearningController | None = None


def get_controller() -> LearningController:
    global _controller
    if _controller is None:
        _controller = LearningController()
    return _controller


def feedback_store() -> FeedbackStore:
    return get_controller().store
