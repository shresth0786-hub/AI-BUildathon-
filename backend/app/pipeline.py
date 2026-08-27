"""
PIPELINE
--------
Runs the full end-to-end flow:

    payment events -> feature engineering -> 3 models -> investigator
                      -> decision + evidence

Exposes:
    * build_full()          : train everything on synthetic data, save artifacts
    * FraudDetector.load()  : load artifacts for live scoring
    * detector.score_event()/investigate_event(): single-payment inference

This is the object FastAPI hosts.
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

from app.data_generator import generate_events
from app.features import FeatureEngineer
from app.models.ml_risk import MLRiskModel, train_ml_risk
from app.models.behaviour_ai import (BehaviourAutoencoder, train_behaviour_ai,
                                     behaviour_scores)
from app.models.graph_engine import GraphEngine, train_graph_engine
from app.investigator import Investigator

_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts")


class FraudDetector:
    def __init__(self):
        self.fe = None
        self.ml_risk: MLRiskModel | None = None
        self.behaviour: BehaviourAutoencoder | None = None
        self.graph: GraphEngine | None = None
        self.investigator: Investigator | None = None
        self.event_df: pd.DataFrame | None = None
        self.feat_df: pd.DataFrame | None = None
        self.summary: dict = {}
        self.tr_idx: np.ndarray | None = None
        self.te_idx: np.ndarray | None = None

    # ------------------------------------------------------------------ build
    def build(self, n_bona_fide: int = 6000, n_fraud: int = 900,
              seed: int = 42, save: bool = True, split: float = 0.8,
              n_reviewish: int = 120) -> dict:
        t0 = time.time()
        events = generate_events(n_bona_fide=n_bona_fide, n_fraud=n_fraud,
                                 seed=seed, n_reviewish=n_reviewish)
        self.event_df = events
        self.fe = FeatureEngineer()
        feat = self.fe.build(events)
        self.feat_df = feat

        # --- train/test split (temporal: features use trailing windows and
        #     per-event data only, so there is no look-ahead leakage)
        n = len(events)
        idx = np.arange(n)
        np.random.seed(seed)
        np.random.shuffle(idx)
        cut = int(n * split)
        tr_idx, te_idx = idx[:cut], idx[cut:]

        # The "borderline / review" population (usr_rev*) is deliberately held
        # OUT of training and evaluation. These are UNSEEN medium-risk payments
        # that the models have never been fit on, so they score as genuinely
        # uncertain (the review band) rather than being memorised as clean.
        rev_mask = events["user_id"].astype(str).str.startswith("usr_rev")
        rev_idx = np.where(rev_mask.values)[0]
        tr_idx = tr_idx[~np.isin(tr_idx, rev_idx)]
        te_idx = te_idx[~np.isin(te_idx, rev_idx)]
        self.tr_idx, self.te_idx = tr_idx, te_idx

        labels = events["true_label"]
        legit_mask = pd.Series(labels.values == 0, index=events.index)

        # ---- 1) ML Risk (supervised) ----
        ml, ml_met = train_ml_risk(feat.iloc[tr_idx], labels.iloc[tr_idx], save=save)

        # ---- 2) Behaviour AI (unsupervised, legit-only) ----
        beh_tr = feat.iloc[tr_idx].copy()
        beh_mask = pd.Series(labels.iloc[tr_idx].values == 0, index=beh_tr.index)
        beh, beh_met = train_behaviour_ai(beh_tr, beh_mask, save=save)

        # ---- 3) Graph Engine (structural) ----
        mask = pd.Series(labels.values == 1, index=events.index)
        grf, grf_met = train_graph_engine(events, mask, save=save)

        # ---- score all data with each model for the investigator stack ----
        p_ml = ml.predict_proba(feat)
        p_beh = behaviour_scores(beh, feat)
        p_grf = grf.score_events(events).values

        # ---- 4) Investigator ensemble ----
        # IMPORTANT: the stacker is fit on the TRAIN split only, so the held-out
        # test-set metrics below are honest (no train/test contamination).
        inv = Investigator()
        inv_met = inv.fit(
            np.column_stack([p_ml[tr_idx], p_beh[tr_idx], p_grf[tr_idx]]),
            labels.values[tr_idx],
            events, feat, grf,
        )

        self.ml_risk, self.behaviour, self.graph, self.investigator = \
            ml, beh, grf, inv
        if save:
            inv.save()

        # ---- track scores on the dataframe for the dashboard ----
        self.feat_df["p_ml"] = p_ml
        self.feat_df["p_behav"] = p_beh
        self.feat_df["p_graph"] = p_grf
        self.feat_df["p_investigator"] = inv.stacker.predict_proba(
            np.column_stack([p_ml, p_beh, p_grf]))[:, 1]
        self.event_df["p_ml"] = p_ml
        self.event_df["p_behav"] = p_beh
        self.event_df["p_graph"] = p_grf
        self.event_df["p_investigator"] = self.feat_df["p_investigator"].values

        test_met = self._held_out_metrics()
        self.summary = {
            "n_events": int(n),
            "n_train": int(len(tr_idx)),
            "n_test": int(len(te_idx)),
            "n_fraud": int(labels.sum()),
            "fraud_rate": float(labels.mean()),
            "ml_auc": ml_met["ml_auc"],
            "behaviour_recon_mean": beh_met["train_recon_mean"],
            "graph_nodes": grf_met["n_nodes"],
            "graph_components": grf_met["n_connected_components"],
            "investigator_auc": inv_met["investigator_auc"],
            "test": test_met,
            "weights": inv_met["weights"],
            "approve_thresh": inv_met["approve_thresh"],
            "review_thresh": inv_met["review_thresh"],
            "feature_cols": len(feat.columns),
            "build_seconds": round(time.time() - t0, 2),
        }
        return self.summary

    # ------------------------------------------------------- held-out metrics
    def _held_out_metrics(self) -> dict:
        """Honest metrics on the held-out TEST split (the ensemble stacker was
        fit on the TRAIN split only, so these are unbiased).

        Cost model (per the AI Risk Manager brief — include false-positive cost):
          - False positive (legit payment blocked/reviewed): costs the merchant
            lost revenue + customer friction. We model `fp_cost` as INR per
            blocked legit payment.
          - False negative (fraud approved): costs the merchant the full
            fraudulent amount (chargeback + fees), scaled by the fraud amount.
        """
        te = self.te_idx
        y = self.event_df["true_label"].values[te]
        p = self.event_df["p_investigator"].values[te]
        a, r = self.investigator.approve_thresh, self.investigator.review_thresh
        dec = np.where(p >= r, "block", np.where(p >= a, "review", "approve"))
        # behaviour-anomaly escalation (must match Investigator.investigate)
        beh = self.event_df["p_behav"].values[te]
        amt = self.event_df["amount_inr"].values[te]
        esc = (dec == "approve") & (beh >= self.investigator.behaviour_review_thresh) \
            & (amt >= self.investigator.behaviour_review_min_amount)
        dec[esc] = "review"

        n_fraud = int(y.sum())
        n_legit = int((y == 0).sum())
        blocked = (dec == "block") & (y == 1)
        gate = (dec != "approve") & (y == 1)
        tp = int(blocked.sum())
        tn = int(((dec == "approve") & (y == 0)).sum())
        fp = int(((dec != "approve") & (y == 0)).sum())
        fn = int(((dec == "approve") & (y == 1)).sum())
        fraud_caught = int(gate.sum())

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0      # fraud recovery
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        # fraud caught including review bucket (reviewed items are manually checked)
        reviewable_recall = fraud_caught / (tp + fn) if (tp + fn) else 0.0

        # ---- cost model ----
        fp_cost_inr = 25.0                                  # blocked legit payment
        te_amounts = self.event_df.loc[te, "amount_inr"].values
        fraud_amounts = te_amounts[y == 1]
        avg_fraud_value = float(fraud_amounts.mean()) if len(fraud_amounts) else 0.0
        fn_cost_inr = avg_fraud_value * 1.1                 # amount + chargeback/fees
        false_positive_cost_inr = fp * fp_cost_inr
        false_negative_cost_inr = fn * fn_cost_inr
        total_cost_inr = false_positive_cost_inr + false_negative_cost_inr
        # baseline: block nothing -> all fraud leaks
        baseline_cost_inr = n_fraud * fn_cost_inr
        prevented_inr = max(0, baseline_cost_inr - total_cost_inr)

        return {
            "n_test": int(len(te)),
            "n_fraud_test": n_fraud,
            "n_legit_test": n_legit,
            "precision": round(precision, 3),
            "recall_fraud_blocked": round(recall, 3),
            "f1": round(f1, 3),
            "fraud_caught": fraud_caught,
            "recall_incl_review": round(reviewable_recall, 3),
            "false_positives": fp,
            "false_negatives": fn,
            "false_positive_cost_inr": round(false_positive_cost_inr, 2),
            "false_negative_cost_inr": round(false_negative_cost_inr, 2),
            "total_cost_inr": round(total_cost_inr, 2),
            "no_intervention_cost_inr": round(baseline_cost_inr, 2),
            "money_prevented_inr": round(prevented_inr, 2),
            "avg_fraud_value_inr": round(avg_fraud_value, 2),
            "approve_thresh": float(a),
            "review_thresh": float(r),
        }

    def test_metrics(self) -> dict:
        """Public accessor for the held-out test metrics (computed at build)."""
        if self.summary and "test" in self.summary:
            return self.summary["test"]
        return self._held_out_metrics()

    # ------------------------------------------------------------------ live
    def score_event(self, event: dict) -> dict:
        """Score a single new payment event (dict) -> core decision."""
        _require(self)
        row = pd.DataFrame([event])
        feat = self.fe.build(row)
        p_ml = float(self.ml_risk.predict_proba(feat)[0])
        p_beh = float(behaviour_scores(self.behaviour, feat)[0])
        p_grf = float(self.graph.score_events(row).values[0])
        p_inv = float(self.investigator.stacker.predict_proba(
            np.array([[p_ml, p_beh, p_grf]]))[0, 0])
        ring = self._detect_ring(row)
        return {
            "event_id": event.get("event_id", "live_" + str(abs(hash(str(event))) % 10**6)),
            "scores": {"ml_risk": round(p_ml, 4), "behaviour_ai": round(p_beh, 4),
                       "graph_engine": round(p_grf, 4), "investigator": round(p_inv, 4)},
            "decision": self._decide(p_inv),
            "risk_ring_hint": ring,
        }

    @staticmethod
    def _normalize_event(event: dict, idx: int) -> dict:
        """Fill raw columns the feature engineer expects, and give the event a
        live id + timestamps when missing (a real webhook may not carry our
        internal event_ts)."""
        e = {**event}
        e.setdefault("event_id", f"live_{abs(hash(str(e))) % 10**8}_{idx}")
        e.setdefault("event_ts", int(time.time_ns()))
        e.setdefault("merchant", "Unknown Store")
        e.setdefault("payment_method", "card")
        e.setdefault("billing_zip", "000000")
        e.setdefault("shipping_zip", e.get("billing_zip", "000000"))
        e.setdefault("status", "captured")
        e.setdefault("is_international", False)
        e.setdefault("ip_geo_match", True)
        e.setdefault("is_new_device", False)
        e.setdefault("typing_seconds", 10.0)
        e.setdefault("attempt_count", 1)
        e.setdefault("three_ds_passed", True)
        e.setdefault("device_id", f"dev_{e['user_id']}")
        e.setdefault("card_last4", "0000")
        e["fraud_vector"] = None
        e["true_label"] = 0
        return e

    def investigate_event(self, event: dict, history: list | None = None) -> dict:
        """Score a fresh payment, optionally with `history` = prior payments
        from the same entity (e.g. a card-testing / velocity burst) that supply
        realistic velocity context. The target event is always scored last."""
        _require(self)
        df = self.event_df.copy()

        prior_rows = []
        if history:
            now = int(time.time_ns())
            base_gap = 8  # seconds between prior attempts
            for i, p in enumerate(reversed(history)):
                pe = self._normalize_event(p, f"prior_{i}")
                pe["event_ts"] = pe.get("event_ts", now - (i + 1) * base_gap * 10**9)
                prior_rows.append(pe)
        target = self._normalize_event(event, "target")
        if history:
            # ensure the target is the most recent event
            target["event_ts"] = max([p["event_ts"] for p in prior_rows] + [target["event_ts"]]) \
                + 1_000_000_000

        rows = prior_rows + [target]
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        feat = self.fe.build(df)
        idx_last = len(df) - 1
        p_ml = float(self.ml_risk.predict_proba(feat)[idx_last:idx_last + 1][0])
        p_beh = float(behaviour_scores(self.behaviour, feat)[idx_last])
        p_grf = float(self.graph.score_events(df).values[idx_last])
        self.investigator.event_df = df
        self.investigator.feat_df = feat
        return self.investigator.investigate(idx_last, p_ml, p_beh, p_grf)

    def _detect_ring(self, row) -> list[str]:
        hints = []
        amt = float(row["amount_inr"].iloc[0])
        if amt >= 3000:
            hints.append("high-value")
        if bool(row["is_international"].iloc[0]):
            hints.append("international")
        return hints

    def _decide(self, p: float) -> str:
        if p >= self.investigator.review_thresh:
            return "block"
        if p >= self.investigator.approve_thresh:
            return "review"
        return "approve"

    # ---------------------------------------------------------------- metrics
    def decision_metrics(self) -> dict:
        _require(self)
        events = self.event_df
        p = events["p_investigator"].values
        y = events["true_label"].values
        a, r = self.investigator.approve_thresh, self.investigator.review_thresh
        dec = np.where(p >= r, "block", np.where(p >= a, "review", "approve"))
        # behaviour-anomaly escalation (must match Investigator.investigate)
        beh = events["p_behav"].values
        amt = events["amount_inr"].values
        esc = (dec == "approve") & (beh >= self.investigator.behaviour_review_thresh) \
            & (amt >= self.investigator.behaviour_review_min_amount)
        dec[esc] = "review"
        return {
            "approve": int((dec == "approve").sum()),
            "review": int((dec == "review").sum()),
            "block": int((dec == "block").sum()),
            "fraud_caught": int(((dec != "approve") & (y == 1)).sum()),
            "fraud_total": int(y.sum()),
            "false_alarms": int(((dec != "approve") & (y == 0)).sum()),
            "leakage": float(((dec == "approve") & (y == 1)).sum() / max(1, y.sum())),
        }

    def decisions(self) -> pd.DataFrame:
        _require(self)
        events = self.event_df.copy()
        p = events["p_investigator"].values
        a, r = self.investigator.approve_thresh, self.investigator.review_thresh
        events["decision"] = np.where(p >= r, "block",
                                      np.where(p >= a, "review", "approve"))
        # behaviour-anomaly escalation (must match Investigator.investigate)
        esc = (events["decision"] == "approve") & (
            events["p_behav"].values >= self.investigator.behaviour_review_thresh) & (
            events["amount_inr"].values >= self.investigator.behaviour_review_min_amount)
        events.loc[esc, "decision"] = "review"
        return events

    # ------------------------------------------------------------------ io
    def save_all(self):
        self.ml_risk.save()
        self.behaviour.save()
        self.graph.save()
        self.investigator.save()
        self.event_df.to_parquet(os.path.join(_ARTIFACT_DIR, "events.parquet"))
        self.feat_df.to_parquet(os.path.join(_ARTIFACT_DIR, "features.parquet"))
        import json
        with open(os.path.join(_ARTIFACT_DIR, "summary.json"), "w") as fh:
            json.dump(self.summary, fh, indent=2)

    @classmethod
    def load(cls):
        import json
        det = cls()
        det.ml_risk = MLRiskModel.load()
        det.behaviour = BehaviourAutoencoder.load()
        det.graph = GraphEngine.load()
        det.investigator = Investigator.load()
        det.event_df = pd.read_parquet(os.path.join(_ARTIFACT_DIR, "events.parquet"))
        det.feat_df = pd.read_parquet(os.path.join(_ARTIFACT_DIR, "features.parquet"))
        det.fe = FeatureEngineer()
        spath = os.path.join(_ARTIFACT_DIR, "summary.json")
        if os.path.exists(spath):
            with open(spath) as fh:
                det.summary = json.load(fh)
        return det


def _require(det: FraudDetector):
    if None in (det.ml_risk, det.behaviour, det.graph, det.investigator):
        raise RuntimeError("FraudDetector not built; run build() first")
