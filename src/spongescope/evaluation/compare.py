"""Paired comparison of two models on the same pairs.

Both models are resampled with the *same* lncRNAs in each bootstrap draw, so the CI is for the
difference itself. That is tighter and more honest than comparing two separate CIs, because the
two models' errors on a given lncRNA are correlated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from spongescope.evaluation.metrics import GROUPS

METRICS = {"auroc": roc_auc_score, "aupr": average_precision_score}


def paired_bootstrap(
    a: pd.DataFrame, b: pd.DataFrame, group: str, n_boot: int = 2000, seed: int = 42
) -> pd.DataFrame:
    """a, b: prediction frames (pair_id, gene_id, label, split, eval_group, score).

    Returns one row per metric: model a, model b, delta = a - b, 95% CI of delta, and
    p_one_sided = share of bootstrap draws where a is not better than b.
    """
    sel_a = a[GROUPS[group](a)][["pair_id", "gene_id", "label", "score"]]
    sel_b = b[GROUPS[group](b)][["pair_id", "score"]]
    d = sel_a.merge(sel_b, on="pair_id", suffixes=("_a", "_b"))
    if len(d) != len(sel_a):
        raise ValueError(f"{group}: models scored different pairs ({len(sel_a)} vs {len(d)})")
    y, pa, pb, g = (d[c].to_numpy() for c in ("label", "score_a", "score_b", "gene_id"))

    uniq, inv = np.unique(g, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    bounds = np.searchsorted(inv[order], np.arange(len(uniq) + 1))
    rows_by_gene = [order[bounds[i] : bounds[i + 1]] for i in range(len(uniq))]
    rng = np.random.default_rng(seed)

    rows = []
    for name, fn in METRICS.items():
        deltas = []
        for _ in range(n_boot):
            idx = np.concatenate([rows_by_gene[i] for i in rng.integers(0, len(uniq), len(uniq))])
            if 0 < y[idx].sum() < len(idx):
                deltas.append(fn(y[idx], pa[idx]) - fn(y[idx], pb[idx]))
        deltas = np.asarray(deltas)
        va, vb = fn(y, pa), fn(y, pb)
        rows.append(
            {
                "group": group,
                "metric": name,
                "model_a": va,
                "model_b": vb,
                "delta": va - vb,
                "ci_lo": float(np.percentile(deltas, 2.5)),
                "ci_hi": float(np.percentile(deltas, 97.5)),
                "p_one_sided": float(np.mean(deltas <= 0)),
            }
        )
    return pd.DataFrame(rows)


def seed_summary(tables: dict[str, pd.DataFrame], metrics=("auroc", "aupr", "ece")) -> pd.DataFrame:
    """Mean and sd across runs (e.g. seeds) per evaluation group."""
    long = pd.concat([t.assign(run=name) for name, t in tables.items()])
    agg = long.groupby("group")[list(metrics)].agg(["mean", "std"])
    agg.columns = [f"{m}_{s}" for m, s in agg.columns]
    agg.insert(0, "n_runs", long.groupby("group")["run"].nunique())
    return agg.reset_index()
