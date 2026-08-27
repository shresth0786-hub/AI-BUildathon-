"""
ML RISK MODEL
-------------
Supervised gradient-boosted fraud-risk scorer trained on labelled events.
Outputs a probability `p_ml` in [0, 1] plus the raw feature vector it used.

Wraps XGBoost with a probability calibration (Platt scaling) so the score is
directly comparable to the Behaviour AI and Graph Engine scores before the
AI Investigator combines them.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score

from app.features import FeatureEngineer

_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts")


class MLRiskModel:
    def __init__(self, feature_cols: list[str] | None = None):
        self.feature_cols = feature_cols
        self.model = None  # CalibratedClassifierCV wrapping XGBClassifier

    def train(self, features: pd.DataFrame, labels: pd.Series) -> dict:
        cols = features.columns.tolist()
        self.feature_cols = cols
        X = features[cols].values.astype(np.float32)
        y = labels.values.astype(np.int32)

        base = xgb.XGBClassifier(
            n_estimators=220,
            max_depth=5,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=1.5,
            eval_metric="auc",
            tree_method="hist",
            random_state=42,
        )
        # Calibrate probabilities (Platt) so the output is a well-calibrated
        # risk score comparable across the three models.
        self.model = CalibratedClassifierCV(base, method="sigmoid", cv=3)

        self.model.fit(X, y)
        pred = self.model.predict_proba(X)[:, 1]
        auc = roc_auc_score(y, pred)
        return {"ml_auc": float(auc), "n_features": len(cols)}

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        _check(self)
        X = features[self.feature_cols].values.astype(np.float32)
        return self.model.predict_proba(X)[:, 1]

    def save(self, path: str | None = None):
        _check(self)
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "ml_risk.joblib")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({"model": self.model, "feature_cols": self.feature_cols}, path)

    @classmethod
    def load(cls, path: str | None = None):
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "ml_risk.joblib")
        payload = joblib.load(path)
        m = cls(feature_cols=payload["feature_cols"])
        m.model = payload["model"]
        return m


def train_ml_risk(features: pd.DataFrame, labels: pd.Series,
                  save: bool = True) -> tuple[MLRiskModel, dict]:
    model = MLRiskModel()
    metrics = model.train(features, labels)
    if save:
        model.save()
    return model, metrics


def _check(m: MLRiskModel):
    if m.model is None or not m.feature_cols:
        raise RuntimeError("MLRiskModel not trained or loaded")
