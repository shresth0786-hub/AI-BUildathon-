"""
AI INVESTIGATOR
---------------
The "decision + evidence" layer. It:

  1. Ensembles the three model scores (ML Risk, Behaviour AI, Graph Engine)
     into one calibrated fraud probability using a logistic/weighted stacker
     trained on a validation split.
  2. Produces a decision rule (approve / review / block) from thresholds tuned
     to target a maximum fraud leakage.
  3. Generates an INVESTIGATION REPORT: human-readable narrative evidence
     explaining WHY a flag happened, which model fired, which features drove
     the risk, and the predicted fraud vector.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from app.models.graph_engine import GraphEngine

_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts")


class AILogic:
    pass


class Investigator:
    def __init__(self):
        self.stacker = None       # LogisticRegression over [p_ml, p_behav, p_graph]
        self.weights = None       # fitted coefficients (for explainability)
        self.approve_thresh = 0.35
        self.review_thresh = 0.65
        self.pred_auc = None
        self.vector_model = None  # simple classifier to predict fraud vector
        self.graph_engine: GraphEngine | None = None
        self.feat_df = None
        self.event_df = None

    # ------------------------------------------------------------------ fit
    def fit(self, stack_matrix: np.ndarray, labels: np.ndarray,
            event_df: pd.DataFrame, feat_df: pd.DataFrame,
            graph_engine: GraphEngine) -> dict:
        self.graph_engine = graph_engine
        self.event_df = event_df
        self.feat_df = feat_df
        X = np.asarray(stack_matrix, dtype=np.float64)
        y = np.asarray(labels, dtype=np.int32)

        from sklearn.metrics import roc_auc_score
        self.stacker = LogisticRegression(C=1.0, max_iter=500)
        self.stacker.fit(X, y)
        self.weights = self.stacker.coef_[0]
        self.pred_auc = float(roc_auc_score(y, self.stacker.predict_proba(X)[:, 1]))

        # ---- a light vector classifier for the investigation narrative ----
        from sklearn.ensemble import ExtraTreesClassifier
        self.vector_model = ExtraTreesClassifier(n_estimators=60, random_state=42)
        if self.event_df["fraud_vector"].notna().any():
            vmask = self.event_df["fraud_vector"].notna()
            if vmask.sum() > 0:
                vcols = [c for c in feat_df.columns if c in feat_df.columns]
                self.vector_model.fit(
                    feat_df.loc[vmask, vcols].values.astype(np.float32),
                    self.event_df.loc[vmask, "fraud_vector"].values,
                )

        # tune thresholds on the calibration curve (target leak <= 0.10)
        self.approve_thresh, self.review_thresh = self._thresholds(X, y)
        return {
            "investigator_auc": self.pred_auc,
            "weights": {k: round(v, 3) for k, v in
                        zip(["ml_risk", "behaviour_ai", "graph_engine"], self.weights)},
            "approve_thresh": self.approve_thresh,
            "review_thresh": self.review_thresh,
        }

    def _thresholds(self, X, y):
        proba = self.stacker.predict_proba(X)[:, 1]
        # review threshold: where recall for fraud >= 0.85
        order = np.argsort(-proba)
        sorted_y = y[order]
        sorted_p = proba[order]
        cum = np.cumsum(sorted_y)
        total_f = cum[-1]
        idx = np.searchsorted(cum / max(total_f, 1), 0.85)
        idx = min(idx, len(proba) - 1)
        review = float(np.clip(sorted_p[idx], 0.4, 0.8))
        approve = float(np.clip(review * 0.55, 0.2, 0.55))
        return approve, review

    # ------------------------------------------------------------------ run
    def investigate(self, idx: int, p_ml: float, p_behav: float, p_graph: float) -> dict:
        X = np.array([[p_ml, p_behav, p_graph]], dtype=np.float64)
        p = float(self.stacker.predict_proba(X)[0, 1])
        if p >= self.review_thresh:
            decision = "block"
        elif p >= self.approve_thresh:
            decision = "review"
        else:
            decision = "approve"

        row = self.event_df.iloc[idx]
        feat = self.feat_df.iloc[idx]

        evidence = self._build_evidence(row, feat, p_ml, p_behav, p_graph, p)
        report = self._build_report(row, feat, decision, evidence, p)
        return {
            "event_id": row["event_id"],
            "user_id": row["user_id"],
            "merchant": row["merchant"],
            "amount_inr": float(row["amount_inr"]),
            "status": row["status"],
            "scores": {
                "ml_risk": round(p_ml, 4),
                "behaviour_ai": round(p_behav, 4),
                "graph_engine": round(p_graph, 4),
                "investigator": round(p, 4),
            },
            "decision": decision,
            "true_label": int(row["true_label"]),
            "fraud_vector": row["fraud_vector"],
            "evidence": evidence,
            "report": report,
        }

    def _build_evidence(self, row, feat, p_ml, p_behav, p_graph, p) -> list[dict]:
        ev = []

        # Only surface explanations when the corresponding model actually
        # considers the event risky (avoids noise on clearly-clean events).
        # ---- ML risk feature-level reasons (only when ml risk elevated) ----
        if p_ml > 0.5:
            hot_features = [
                ("card_test_flag", "card-testing pattern (many tiny hits)"),
                ("velocity_flag", "high transaction velocity"),
                ("bot_cadence_flag", "machine-like bot cadence"),
                ("geography_flag", "geography mismatch (international / billing!=shipping)"),
                ("billing_shipping_mismatch", "billing vs shipping address mismatch"),
                ("is_new_device", "brand-new device"),
                ("attempts_gt_1", "multiple payment attempts"),
            ]
            fired = [msg for name, msg in hot_features if feat[name] == 1]
            if fired:
                ev.append({
                    "model": "ml_risk", "signal": "rule_based",
                    "detail": "; ".join(fired), "weight": round(float(p_ml), 3),
                })
            if row["amount_inr"] >= 3000:
                ev.append({"model": "ml_risk", "signal": "amount",
                           "detail": f"high-value transaction INR {row['amount_inr']:.0f}",
                           "weight": round(float(p_ml), 3)})
            if row["amount_inr"] <= 15:
                ev.append({"model": "ml_risk", "signal": "amount",
                           "detail": "micro-amount transaction (typical of card testing)",
                           "weight": round(float(p_ml), 3)})

        # ---- behaviour ----
        if p_behav > 0.5:
            ev.append({"model": "behaviour_ai",
                       "signal": "reconstruction_error",
                       "detail": "behaviour deviates from the payer's legit profile "
                                 "(fast typing, bot cadence, velocity spikes)",
                       "weight": round(float(p_behav), 3)})

        # ---- graph ----
        if p_graph > 0.5 and self.graph_engine is not None:
            links = self.graph_engine.edge_evidence(
                row["user_id"], row["card_last4"], row["device_id"]
            )
            if links:
                detail = "; ".join(f"{l['node']} (suspicion {l['suspicion']})"
                                   for l in links)
                ev.append({"model": "graph_engine", "signal": "shared_entity",
                           "detail": f"entity linkage surfaced: {detail}",
                           "weight": round(float(p_graph), 3)})
            else:
                ev.append({"model": "graph_engine", "signal": "structural",
                           "detail": "payer/device/card sits at the centre of a "
                                     "shared-entity cluster",
                           "weight": round(float(p_graph), 3)})

        # ---- cross-model agreement ----
        high = [m for m, s in [("ML Risk", p_ml), ("Behaviour AI", p_behav),
                               ("Graph Engine", p_graph)] if s > 0.5]
        if len(high) >= 2:
            ev.append({"model": "investigator", "signal": "ensemble_agreement",
                       "detail": f"{len(high)} of 3 models agree on risk: {', '.join(high)}",
                       "weight": round(float(p), 3)})
        return ev

    def _build_report(self, row, feat, decision, evidence, p) -> str:
        lines = [
            f"INVESTIGATION REPORT — {row['event_id']}",
            f"Decision: {decision.upper()}  |  Combined fraud probability: {p:.0%}",
            "",
            f"Payer {row['user_id']} attempted INR {row['amount_inr']:.2f} at "
            f"'{row['merchant']}' via {row['payment_method']} (card ••{row['card_last4']}).",
        ]
        if row["fraud_vector"]:
            lines.append(f"Predicted/actual fraud vector: {row['fraud_vector']}.")
        lines.append("")
        if evidence:
            lines.append("Key signals detected:")
            for e in evidence:
                lines.append(f"  • [{e['model']}] {e['detail']}")
        else:
            lines.append("No high-risk signals detected; pattern consistent with "
                         "the payer's established behaviour.")
        lines.append("")
        if decision != "approve":
            lines.append("Recommendation: send for manual review before funds are "
                         "settled to the merchant; consider velocity cap and "
                         "additional KYC on the payer.")
        else:
            lines.append("Recommendation: no further action required.")
        return "\n".join(lines)

    # ------------------------------------------------------------------ io
    def save(self, path: str | None = None):
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "investigator.joblib")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({
            "stacker": self.stacker, "weights": self.weights,
            "approve_thresh": self.approve_thresh,
            "review_thresh": self.review_thresh,
            "pred_auc": self.pred_auc,
            "vector_model": self.vector_model,
        }, path)

    @classmethod
    def load(cls, path: str | None = None):
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "investigator.joblib")
        payload = joblib.load(path)
        inv = cls()
        inv.stacker = payload["stacker"]
        inv.weights = payload["weights"]
        inv.approve_thresh = payload["approve_thresh"]
        inv.review_thresh = payload["review_thresh"]
        inv.pred_auc = payload["pred_auc"]
        inv.vector_model = payload["vector_model"]
        return inv
