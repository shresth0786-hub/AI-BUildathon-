"""
train.py
--------
One-shot script that trains the full fraud-detection stack on synthetic
Razorpay-style payment events and persists every artifact to artifacts/.

Run from the backend/ directory:

    python train.py [--n-bona-fide 6000] [--n-fraud 900] [--seed 42]
"""

from __future__ import annotations

import argparse

from app.pipeline import FraudDetector


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-bona-fide", type=int, default=6000)
    ap.add_argument("--n-fraud", type=int, default=900)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    detector = FraudDetector()
    summary = detector.build(
        n_bona_fide=args.n_bona_fide,
        n_fraud=args.n_fraud,
        seed=args.seed,
        save=True,
    )
    detector.save_all()

    print("\n=== TRAINING SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k:20s} : {v}")
    print("\n=== DECISION METRICS ===")
    for k, v in detector.decision_metrics().items():
        print(f"  {k:20s} : {v}")
    print("\nArtifacts written to backend/artifacts/")


if __name__ == "__main__":
    main()
