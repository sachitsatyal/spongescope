"""Classic baselines: logistic regression / gradient boosting on hand-crafted features.

Each feature set is one MLflow run; predictions go to data/predictions/<name>.parquet.
"""

from __future__ import annotations

import hydra
import mlflow
import numpy as np
import pandas as pd
from omegaconf import DictConfig
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from spongescope import tracking
from spongescope.baselines.features import FEATURE_SETS, build_pair_features
from spongescope.data.paper_style import paper_style_pairs
from spongescope.evaluation.metrics import evaluate
from spongescope.features.common import project_path


def make_model(name: str, seed: int):
    if name == "gbm_all":
        return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=seed)
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="baselines")
def main(cfg: DictConfig) -> None:
    proc = project_path(cfg.paths.processed)
    pairs = pd.read_parquet(proc / "fct_pairs.parquet")
    lnc = pd.read_parquet(proc / "dim_lncrna.parquet")
    mir = pd.read_parquet(proc / "dim_mirna.parquet")

    suffix = ""
    if cfg.paper_style:
        pairs = paper_style_pairs(pairs, cfg.seed)
        suffix = "_paper"
        print(f"paper-style data: {len(pairs):,} pairs, positive rate {pairs.label.mean():.2f}")
    feat_path = project_path(cfg.paths.features) / f"classic_pair_features{suffix}.parquet"
    data = pd.read_parquet(feat_path) if feat_path.exists() else None
    if data is not None and set(data.pair_id) != set(pairs.pair_id):
        print("pairs changed since features were cached -> rebuilding")
        data = None
    if data is not None:
        data = data.drop(columns=[c for c in pairs.columns if c != "pair_id"], errors="ignore")
        data = pairs.merge(data, on="pair_id", how="left")
    else:
        data = build_pair_features(
            pairs, lnc, mir, project_path(cfg.paths.features) / "accessibility"
        )
        data.to_parquet(feat_path, index=False)

    train = data[data.split == "train"]
    evals = data[data.split.isin(["val", "test"])].copy()
    tracking.setup(cfg)
    keep = ["pair_id", "gene_id", "mimat_id", "label", "split", "eval_group", "has_seed_site"]
    data_version = tracking.dataset_hash(proc / "fct_pairs.parquet")

    for name, cols in FEATURE_SETS.items():
        model = make_model(name, cfg.seed)
        model.fit(train[cols].to_numpy(), train.label.to_numpy())
        preds = evals[keep].copy()
        preds["score"] = model.predict_proba(evals[cols].to_numpy())[:, 1]
        table = evaluate(preds, n_boot=cfg.eval.n_boot, seed=cfg.seed)

        with mlflow.start_run(run_name=f"classic/{name}{suffix}"):
            mlflow.set_tags({"family": "classic", "model": name})
            mlflow.log_params(
                {
                    "features": ",".join(cols),
                    "estimator": type(model).__name__,
                    "data_version": data_version,
                    "paper_style": str(cfg.paper_style),
                }
            )
            tracking.log_results(
                table, preds, project_path(cfg.paths.predictions) / f"{name}{suffix}.parquet"
            )

        row = table.set_index("group")
        parts = [
            f"{g.removeprefix('test_')} {row.at[g, 'auroc']:.3f}/{row.at[g, 'aupr']:.3f}"
            for g in ["test_cold_lncrna", "test_cold_both", "test_seed_controlled", "test_paper"]
            if g in row.index
        ]
        print(f"{name:<18} AUROC/AUPR  " + " | ".join(parts))
    grp = "paper" if cfg.paper_style else "cold_lncrna"
    print(f"positive rate (test {grp}): {np.mean(evals[evals.eval_group == grp].label):.3f}")


if __name__ == "__main__":
    main()
