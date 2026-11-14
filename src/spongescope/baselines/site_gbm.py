"""site_gbm: gradient boosting on per-pair aggregates of the candidate-site table.

Same scanner as the SpongeScope model, no neural network -> shows how much the scanner alone
buys, so the neural model has to beat this too.
"""

from __future__ import annotations

import hydra
import mlflow
import numpy as np
import pandas as pd
from omegaconf import DictConfig
from sklearn.ensemble import HistGradientBoostingClassifier

from spongescope import tracking
from spongescope.evaluation.metrics import evaluate
from spongescope.features.common import project_path
from spongescope.features.sites import COUNT_COLS


def pair_features(pair_tab: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    s = sites.copy()
    s["is_best"] = s.groupby("pair_id")["type_id"].transform("min") == s["type_id"]
    agg = s.groupby("pair_id").agg(
        best_type=("type_id", "min"),
        max_acc_site=("acc_site", "max"),
        mean_acc_site=("acc_site", "mean"),
        max_acc_u14=("acc_u14", "max"),
        max_supp=("supp", "max"),
        mean_au_local=("au_local", "mean"),
    )
    best_acc = s[s.is_best].groupby("pair_id")["acc_site"].max().rename("best_site_acc")
    f = pair_tab.set_index("pair_id").join(agg).join(best_acc)
    f["best_type"] = f["best_type"].fillna(len(COUNT_COLS))
    return f.fillna(0.0)


FEATURES = [
    *COUNT_COLS,
    "n_sites",
    "log_len",
    "best_type",
    "max_acc_site",
    "mean_acc_site",
    "max_acc_u14",
    "max_supp",
    "mean_au_local",
    "best_site_acc",
]


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="baselines")
def main(cfg: DictConfig) -> None:
    proc, feat = project_path(cfg.paths.processed), project_path(cfg.paths.features)
    pairs = pd.read_parquet(proc / "fct_pairs.parquet")
    f = pair_features(
        pd.read_parquet(feat / "sites" / "pairs.parquet"),
        pd.read_parquet(feat / "sites" / "sites.parquet"),
    )
    # Only id/label/split columns from fct_pairs: it also holds CLIP-derived columns
    # (e.g. n_sites, max_clip_exp_num for positives) that must never become features.
    keep = ["pair_id", "gene_id", "mimat_id", "label", "split", "eval_group", "has_seed_site"]
    data = pairs[keep].join(f[FEATURES], on="pair_id")
    train = data[data.split == "train"]
    evals = data[data.split.isin(["val", "test"])].copy()

    model = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, random_state=cfg.seed)
    model.fit(train[FEATURES].to_numpy(), train.label.to_numpy())
    preds = evals[keep].copy()
    preds["score"] = model.predict_proba(evals[FEATURES].to_numpy())[:, 1]
    table = evaluate(preds, n_boot=cfg.eval.n_boot, seed=cfg.seed)

    tracking.setup(cfg)
    with mlflow.start_run(run_name="classic/site_gbm"):
        mlflow.set_tags({"family": "classic", "model": "site_gbm"})
        mlflow.log_params(
            {
                "features": ",".join(FEATURES),
                "data_version": tracking.dataset_hash(proc / "fct_pairs.parquet"),
            }
        )
        tracking.log_results(table, preds, project_path(cfg.paths.predictions) / "site_gbm.parquet")
    cols = ["group", "n_pos", "n_neg", "auroc", "aupr", "per_lnc_auroc", "ece"]
    print(table[cols].round(3).to_string(index=False))
    print(f"no-site share (test): {np.mean(evals[evals.split == 'test'].n_sites == 0):.3f}")


if __name__ == "__main__":
    main()
