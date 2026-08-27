"""
BEHAVIOUR AI
------------
Unsupervised behavioural-anomaly detector. A lightweight under-complete
autoencoder is trained ONLY on legitimate (bona-fide) behaviour. At inference
time we reconstruct each event's behaviour vector and score the reconstruction
error. Fraudulent behaviour (bots, bursts, testing) reconstructs poorly, giving
a high anomaly score -> high fraud probability `p_behav`.

Because complete data is large, we drive the autoencoder with numpy + closed
form weights initialised once and fine-tuned with a few SGD steps. This keeps
the buildathon demo dependency-light while still being a genuine neural model.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts")


class BehaviourAutoencoder:
    """Single-hidden-layer under-complete autoencoder, trained in pure numpy."""

    def __init__(self, hidden: int = 12, epochs: int = 60, lr: float = 2e-2,
                 random_state: int = 42):
        self.hidden = hidden
        self.epochs = epochs
        self.lr = lr
        self.rs = random_state
        self.W1 = None
        self.b1 = None
        self.W2 = None
        self.b2 = None
        self.mean_ = None
        self.std_ = None
        self.fit_threshold_ = None

    # ---- forward / backward ----------------------------------------------
    def _encode(self, X):
        return np.tanh(X @ self.W1 + self.b1)

    def _decode(self, H):
        return H @ self.W2 + self.b2

    def _recon_error(self, X):
        return np.mean((X - self._decode(self._encode(X))) ** 2, axis=1)

    # ---- training ----------------------------------------------------------
    def train(self, X: np.ndarray) -> dict:
        X = np.asarray(X, dtype=np.float64)
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0) + 1e-8
        Xn = (X - self.mean_) / self.std_

        rng = np.random.RandomState(self.rs)
        n, d = Xn.shape
        h = self.hidden
        self.W1 = rng.normal(0, np.sqrt(2 / d), (d, h))
        self.b1 = np.zeros(h)
        self.W2 = rng.normal(0, np.sqrt(2 / h), (h, d))
        self.b2 = np.zeros(d)

        for _ in range(self.epochs):
            H = np.tanh(Xn @ self.W1 + self.b1)
            Xr = H @ self.W2 + self.b2
            dXr = (Xn - Xr) / Xn.shape[0]

            # backprop through decoder then encoder
            dW2 = H.T @ dXr
            db2 = dXr.sum(axis=0)
            dH = dXr @ self.W2.T
            dAct = dH * (1 - H ** 2)
            dW1 = Xn.T @ dAct
            db1 = dAct.sum(axis=0)

            for param, grad in ((self.W1, dW1), (self.b1, db1),
                                (self.W2, dW2), (self.b2, db2)):
                param += self.lr * grad

        err = self._recon_error(Xn)
        self.fit_threshold_ = np.percentile(err, 95)
        return {"train_recon_mean": float(err.mean()),
                "fit_threshold_95": float(self.fit_threshold_)}

    # ---- inference -----------------------------------------------------------
    def anomaly_scores(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        Xn = (X - self.mean_) / self.std_
        err = self._recon_error(Xn)
        # scale so fit_threshold_ maps to p=0.5 (calibrated-ish fraud prob)
        if self.fit_threshold_ is None or self.fit_threshold_ <= 0:
            return np.clip(err, 0, 1)
        p = 1.0 / (1.0 + np.exp(-5.0 * (err / self.fit_threshold_ - 1.0)))
        return p

    def save(self, path: str | None = None):
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "behaviour_ai.joblib")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({k: v for k, v in self.__dict__.items()}, path)

    @classmethod
    def load(cls, path: str | None = None):
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "behaviour_ai.joblib")
        m = cls()
        m.__dict__.update(joblib.load(path))
        return m


# Behavioural feature set (subset of engineered features that describe HOW a
# human pays, independent of locale). Standardised in the model.
BEHAVIOUR_FEATURES = [
    "amount_log", "amount_round", "attempts_gt_1", "typing_seconds",
    "typing_very_fast", "is_night", "recent_failure_rate", "is_new_device",
    "method_mix_entropy", "count_card_60m", "count_user_60m", "count_device_60m",
]


def train_behaviour_ai(features: pd.DataFrame, legitimate_mask: pd.Series,
                       save: bool = True) -> tuple[BehaviourAutoencoder, dict]:
    legit = features.loc[legitimate_mask, BEHAVIOUR_FEATURES].values
    model = BehaviourAutoencoder()
    metrics = model.train(legit)
    if save:
        model.save()
    return model, metrics


def behaviour_scores(model: BehaviourAutoencoder,
                     features: pd.DataFrame) -> np.ndarray:
    X = features[BEHAVIOUR_FEATURES].values
    return model.anomaly_scores(X)
