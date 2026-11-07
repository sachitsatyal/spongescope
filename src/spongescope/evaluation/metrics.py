"""Evaluation used by every model, so all numbers in the benchmark are comparable.

Groups: val, test (all), test_cold_lncrna, test_cold_both,
test_seed_controlled (cold test pairs whose lncRNA has a 7mer site for the miRNA - seed
matching cannot separate these, so it measures what a model adds beyond seeds), and the
sanity-check groups test_warm (random pair split, balanced negatives) and test_paper
(original paper setup: random 1:1 negatives + random pair split).
Per group: AUROC, AUPR, AUPR lift over the positive rate, expected calibration error,
mean per-lncRNA AUROC (each lncRNA ranks its own miRNAs - immune to hub/length shortcuts),
and 95% CIs from a bootstrap that resamples whole lncRNAs (pairs of one lncRNA are not
independent).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

GROUPS = {
    "val": lambda d: d["split"] == "val",
    "test": lambda d: d["split"] == "test",
    "test_cold_lncrna": lambda d: d["eval_group"] == "cold_lncrna",
    "test_cold_both": lambda d: d["eval_group"] == "cold_both",
    "test_seed_controlled": lambda d: (
        d["eval_group"].isin(["cold_lncrna", "cold_both"])
        & d.get("has_seed_site", pd.Series(False, index=d.index)).fillna(False).astype(bool)
    ),
    "test_warm": lambda d: d["eval_group"] == "warm",
    "test_paper": lambda d: d["eval_group"] == "paper",
}


def expected_calibration_error(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    bins = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        m = bins == b
        if m.any():
            ece += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(ece)


def per_lncrna_auroc(genes: np.ndarray, y: np.ndarray, p: np.ndarray) -> float:
    vals = []
    for g in np.unique(genes):
        m = genes == g
        if 0 < y[m].sum() < m.sum():
            vals.append(roc_auc_score(y[m], p[m]))
    return float(np.mean(vals)) if vals else float("nan")


def _bootstrap(genes, y, p, n_boot: int, seed: int) -> dict[str, tuple[float, float]]:
    rng = np.random.default_rng(seed)
    uniq = np.unique(genes)
    order = np.argsort(genes, kind="stable")
    starts = np.searchsorted(genes[order], uniq)
    ends = np.append(starts[1:], len(genes))
    idx_by_gene = [order[s:e] for s, e in zip(starts, ends, strict=True)]
    au, ap = [], []
    for _ in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        idx = np.concatenate([idx_by_gene[i] for i in pick])
        yb = y[idx]
        if 0 < yb.sum() < len(yb):
            au.append(roc_auc_score(yb, p[idx]))
            ap.append(average_precision_score(yb, p[idx]))

    def ci(v: list[float]) -> tuple[float, float]:
        return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

    return {"auroc": ci(au), "aupr": ci(ap)}


def evaluate(
    df: pd.DataFrame, score_col: str = "score", n_boot: int = 1000, seed: int = 42
) -> pd.DataFrame:
    """df needs: gene_id, label, split, eval_group, <score_col> (probability in [0, 1])."""
    rows = []
    for name, sel in GROUPS.items():
        d = df[sel(df)]
        if d.empty or d["label"].nunique() < 2:
            continue
        y = d["label"].to_numpy().astype(int)
        p = d[score_col].to_numpy().astype(float)
        g = d["gene_id"].to_numpy()
        auroc, aupr = roc_auc_score(y, p), average_precision_score(y, p)
        ci = (
            _bootstrap(g, y, p, n_boot, seed)
            if n_boot
            else {"auroc": (np.nan,) * 2, "aupr": (np.nan,) * 2}
        )
        rows.append(
            {
                "group": name,
                "n_pos": int(y.sum()),
                "n_neg": int(len(y) - y.sum()),
                "pos_rate": float(y.mean()),
                "auroc": auroc,
                "auroc_lo": ci["auroc"][0],
                "auroc_hi": ci["auroc"][1],
                "aupr": aupr,
                "aupr_lo": ci["aupr"][0],
                "aupr_hi": ci["aupr"][1],
                "aupr_lift": aupr / y.mean(),
                "per_lnc_auroc": per_lncrna_auroc(g, y, p),
                "ece": expected_calibration_error(y, p),
            }
        )
    return pd.DataFrame(rows)


def flatten(table: pd.DataFrame) -> dict[str, float]:
    """{'test_cold_lncrna/aupr': 0.31, ...} for MLflow."""
    out = {}
    for _, r in table.iterrows():
        for k, v in r.items():
            if k != "group" and pd.notna(v):
                out[f"{r['group']}/{k}"] = float(v)
    return out
