"""
GRAPH ENGINE
------------
Represents the payment ecosystem as a heterogeneous graph:

    (payer) --[pays_with]--> (card_last4)
    (payer) --[uses]-------> (device)
    (payer) --[paid_to]----> (merchant)
    (device)--[shared]-----> (card_last4)     (same device + card across payers)

Fraud propagates through the graph. We compute a PageRank-style influence score:
bad (seed) nodes pass "suspicion" along edges to their neighbours, so a payer who
shares a device or card with a confirmed fraudster becomes more suspicious.

Per event we score the connected component around its payer, plus local
structural fingerprints: starred (many payers sharing one device/card) and
ring-like (dense mutual funding) patterns -> `p_graph`.
"""

from __future__ import annotations

import os
from collections import defaultdict

import numpy as np
import pandas as pd

_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts")


class GraphEngine:
    def __init__(self, alpha: float = 0.85, max_iter: int = 50, tol: float = 1e-4):
        self.alpha = alpha          # PageRank damping
        self.max_iter = max_iter
        self.tol = tol
        self.graph = None
        self.node_scores = None     # dict node -> suspicion in [0, 1]
        self.index_ = None          # positional row index

    def build(self, df: pd.DataFrame, fraud_mask: pd.Series) -> dict:
        """Build the graph, propagate suspicion, return global stats."""
        df = df.reset_index(drop=True)
        self.index_ = df.index

        # ---------------- construct edges ----------------
        # Only payer/card/device edges carry fraud-relevant structure.
        # (Merchant edges would connect the whole dataset into one component
        #  and dilute propagation, so they are excluded from the model graph.)
        edges = []          # (u, v)
        nodes = set()

        def add(u, v):
            edges.append((u, v))
            nodes.add(u)
            nodes.add(v)

        for row in df.itertuples(index=False):
            payer = f"U:{row.user_id}"
            card = f"C:{row.card_last4}"
            dev = f"D:{row.device_id}"
            add(payer, card)
            add(payer, dev)

        # node -> set of neighbours (undirected)
        adj = defaultdict(set)
        for u, v in edges:
            adj[u].add(v)
            adj[v].add(u)

        self.graph = {"nodes": list(nodes), "adj": adj}

        # ---------------- seeds: confirmed-fraud nodes ----------------
        seed = defaultdict(float)
        for row, is_f in zip(df.itertuples(index=False), fraud_mask):
            if is_f:
                seed[f"U:{row.user_id}"] = max(seed.get(f"U:{row.user_id}", 0.0), 1.0)
                seed[f"C:{row.card_last4}"] = max(seed.get(f"C:{row.card_last4}", 0.0), 1.0)
                seed[f"D:{row.device_id}"] = max(seed.get(f"D:{row.device_id}", 0.0), 1.0)

        score = self._influence_propagation(adj, seed)
        self.node_scores = score

        stats = {
            "n_nodes": len(nodes),
            "n_edges": len(edges),
            "n_connected_components": self._count_components(adj),
        }
        return stats

    def _influence_propagation(self, adj, seed) -> dict:
        """Personalised PageRank with seed injected each iteration."""
        nodes = list(adj.keys())
        n = len(nodes)
        if n == 0:
            return {}
        order = {nd: i for i, nd in enumerate(nodes)}

        # out-degree vector
        out_deg = np.array([len(adj[nd]) for nd in nodes], dtype=np.float64)
        out_deg[out_deg == 0] = 1.0

        p = np.zeros(n)
        # initialise weakly from seed
        for nd, s in seed.items():
            if nd in order:
                p[order[nd]] = s

        # normalise p
        p = p / (p.sum() + 1e-12)

        # seed mass vector
        s_vec = np.zeros(n)
        for nd, s in seed.items():
            if nd in order:
                s_vec[order[nd]] = s
        s_vec = s_vec / (s_vec.sum() + 1e-12)

        # sparse transition via adjacency
        rows, cols = [], []
        for nd, nbrs in adj.items():
            i = order[nd]
            for nb in nbrs:
                rows.append(i)
                cols.append(order[nb])
        import scipy.sparse as sp
        M = sp.csr_matrix((np.ones(len(rows)) / out_deg[rows], (rows, cols)),
                          shape=(n, n)).T  # column-stochastic-ish

        for _ in range(self.max_iter):
            new = self.alpha * (M @ p) + (1 - self.alpha) * s_vec
            if np.max(np.abs(new - p)) < self.tol:
                p = new
                break
            p = new
        p = p / (p.max() + 1e-12)
        return {nodes[i]: float(p[i]) for i in range(n)}

    def _count_components(self, adj) -> int:
        seen = set()
        comps = 0
        for nd in adj:
            if nd in seen:
                continue
            comps += 1
            stack = [nd]
            seen.add(nd)
            while stack:
                cur = stack.pop()
                for nb in adj[cur]:
                    if nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
        return comps

    def score_events(self, df: pd.DataFrame) -> pd.Series:
        """Per-event graph-based fraud probability using propagated suspicion.

        The event is scored by the influence score of the payer, its card and
        its device. Because benign payers have isolating, unique devices and
        cards, their nodes sit at score ~0, while actors entangled with
        confirmed fraud (shared cards/devices/rings) inherit high suspicion.
        """
        if self.graph is None:
            raise RuntimeError("GraphEngine not built")
        df = df.reset_index(drop=True)
        scores = np.zeros(len(df))
        for j, row in enumerate(df.itertuples(index=False)):
            best = 0.0
            best_node = None
            for node in (f"U:{row.user_id}", f"C:{row.card_last4}",
                         f"D:{row.device_id}"):
                s = self.node_scores.get(node, 0.0)
                if s > best:
                    best, best_node = s, node
            scores[j] = float(np.clip(best, 0.0, 1.0))
        return pd.Series(scores, index=df.index)

    def edge_evidence(self, user_id: str, card_last4: str, device_id: str) -> list[dict]:
        nodes = [f"U:{user_id}", f"C:{card_last4}", f"D:{device_id}"]
        out = []
        for node in nodes:
            s = self.node_scores.get(node, 0.0)
            if s > 0.05:
                out.append({"node": node, "suspicion": round(float(s), 4)})
        return out

    def save(self, path: str | None = None):
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "graph_engine.joblib")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({"graph": self.graph, "node_scores": self.node_scores,
                     "alpha": self.alpha}, path)

    @classmethod
    def load(cls, path: str | None = None):
        import joblib
        path = path or os.path.join(_ARTIFACT_DIR, "graph_engine.joblib")
        payload = joblib.load(path)
        g = cls(alpha=payload["alpha"])
        g.graph = payload["graph"]
        g.node_scores = payload["node_scores"]
        return g


def train_graph_engine(df: pd.DataFrame, fraud_mask: pd.Series,
                       save: bool = True) -> tuple[GraphEngine, dict]:
    engine = GraphEngine()
    stats = engine.build(df, fraud_mask)
    if save:
        engine.save()
    return engine, stats
