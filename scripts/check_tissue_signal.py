"""Does tissue context carry pair-level signal? Gradient-boosted check, no GPU, ~1 minute.

Trains the same HistGradientBoosting model twice -- site features alone, then site + tissue
features -- and reports AUPR on each evaluation group with a PAIRED lncRNA-level bootstrap of
the difference. Per the resolution-limit finding (benchmark CI half-width +/-0.03-0.05 AUPR),
a tissue signal that a GBM cannot find is not worth wiring into the neural model.

Usage:
    uv run python scripts/check_tissue_signal.py
    uv run python scripts/check_tissue_signal.py --out reports/tissue_signal.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

# Evaluation groups as pandas query strings, matching the values stored in fct_pairs.eval_group.
# Cold groups are the ones that matter: a warm row reuses an lncRNA the model trained on.
GROUPS: dict[str, str] = {
    "val": "split == 'val'",
    "test": "split == 'test'",
    "test_cold_lncrna": "split == 'test' and eval_group == 'cold_lncrna'",
    "test_cold_both": "split == 'test' and eval_group == 'cold_both'",
    "test_seed_controlled": (
        "split == 'test' and eval_group in ('cold_lncrna', 'cold_both') "
        "and (label == 1 or pair_type == 'seed_matched')"
    ),
}

TISSUE_COLS = [
    "mirna_atlas_known",
    "n_shared_organs",
    "coexpr",
    "max_cooccur",
    "mean_cooccur",
    "lnc_max_level",
    "mir_max_level",
    "lnc_broad_frac",
    "mir_broad_frac",
    "lnc_n_expressed_tissues",
    "lnc_tau",
]


def load(db: Path, sites: Path) -> tuple[pd.DataFrame, list[str]]:
    con = duckdb.connect(str(db), read_only=True)
    try:
        # Only id/label/split columns from fct_pairs: its CLIP-derived columns (n_sites,
        # cell_contexts) are label-derived and must never become features.
        pairs = con.execute(
            "select pair_id, gene_id, mimat_id, label, split, eval_group, pair_type "
            "from marts.fct_pairs"
        ).df()
        tissue = con.execute(
            f"select pair_id, {', '.join(TISSUE_COLS)} from marts.fct_pair_tissue_features"
        ).df()
    finally:
        con.close()

    site = pd.read_parquet(sites)
    site_cols = [c for c in site.columns if c.startswith(("n_", "acc_", "best_", "mean_", "max_"))]
    site = site[["pair_id", *site_cols]]

    df = pairs.merge(site, on="pair_id", how="left").merge(tissue, on="pair_id", how="left")
    df["mirna_atlas_known"] = df["mirna_atlas_known"].astype(float)
    return df, site_cols


def fit_score(train: pd.DataFrame, cols: list[str], target: pd.DataFrame, seed: int) -> np.ndarray:
    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.06,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=seed,
    )
    model.fit(train[cols].to_numpy(dtype=np.float64), train["label"].to_numpy())
    return model.predict_proba(target[cols].to_numpy(dtype=np.float64))[:, 1]


def paired_bootstrap(
    d: pd.DataFrame, a: str, b: str, n: int = 2000, seed: int = 0
) -> dict[str, float]:
    """Bootstrap the DIFFERENCE in AUPR, resampling lncRNAs (not rows) with replacement."""
    genes = d["gene_id"].unique()
    index = {g: np.flatnonzero(d["gene_id"].to_numpy() == g) for g in genes}
    y = d["label"].to_numpy()
    sa, sb = d[a].to_numpy(), d[b].to_numpy()
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        pick = rng.choice(genes, size=len(genes), replace=True)
        rows = np.concatenate([index[g] for g in pick])
        if len(np.unique(y[rows])) < 2:
            continue
        diffs.append(
            average_precision_score(y[rows], sb[rows]) - average_precision_score(y[rows], sa[rows])
        )
    diffs = np.asarray(diffs)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {
        "delta_aupr": float(average_precision_score(y, sb) - average_precision_score(y, sa)),
        "ci_lo": float(lo),
        "ci_hi": float(hi),
        "significant": bool(lo > 0),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/spongescope.duckdb"))
    ap.add_argument("--sites", type=Path, default=Path("data/features/sites/pairs.parquet"))
    ap.add_argument("--out", type=Path, default=Path("reports/tissue_signal.json"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    df, site_cols = load(args.db, args.sites)
    print(
        f"{len(df):,} pairs | {len(site_cols)} site features | {len(TISSUE_COLS)} tissue features"
    )

    cov = df[TISSUE_COLS].notna().mean()
    print("\nCoverage (non-null rate):")
    for c, v in cov.items():
        print(f"  {c:28s} {v:6.1%}")

    train = df[df["split"] == "train"]
    with_t = [*site_cols, *TISSUE_COLS]
    df["score_site"] = fit_score(train, site_cols, df, args.seed)
    df["score_both"] = fit_score(train, with_t, df, args.seed)

    # Univariate check: each tissue feature on its own, cold test rows.
    cold = df.query("split == 'test' and eval_group in ('cold_lncrna', 'cold_both')")
    print("\nUnivariate AUROC on cold test rows (0.5 = no signal):")
    uni = {}
    for c in TISSUE_COLS:
        v = cold[c].to_numpy(dtype=np.float64)
        ok = np.isfinite(v)
        if ok.sum() < 100 or len(np.unique(cold["label"].to_numpy()[ok])) < 2:
            continue
        auc = roc_auc_score(cold["label"].to_numpy()[ok], v[ok])
        uni[c] = float(auc)
        print(f"  {c:28s} {auc:5.3f}  (n={ok.sum():,})")

    print("\nGroup                   AUPR site  AUPR +tissue   delta        95% CI        signif")
    results = {}
    for name, where in GROUPS.items():
        d = df.query(where)
        if d.empty or d["label"].nunique() < 2:
            continue
        a = average_precision_score(d["label"], d["score_site"])
        b = average_precision_score(d["label"], d["score_both"])
        boot = paired_bootstrap(d, "score_site", "score_both", seed=args.seed)
        results[name] = {"aupr_site": float(a), "aupr_tissue": float(b), **boot}
        print(
            f"  {name:22s} {a:8.3f} {b:12.3f} {boot['delta_aupr']:+9.3f}  "
            f"[{boot['ci_lo']:+.3f}, {boot['ci_hi']:+.3f}]  {'YES' if boot['significant'] else 'no'}"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"coverage": cov.to_dict(), "univariate_auroc": uni, "groups": results}, indent=2
        )
    )
    print(f"\nwrote {args.out}")

    key = results.get("test_cold_lncrna")
    if key:
        verdict = (
            "tissue features help -- wire them into the neural model"
            if key["significant"]
            else "no measurable gain -- do NOT wire tissue features into the neural model"
        )
        print(f"\nVERDICT (test_cold_lncrna): {verdict}")


if __name__ == "__main__":
    main()
