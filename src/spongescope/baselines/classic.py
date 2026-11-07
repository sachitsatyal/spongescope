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

    feat_path = project_path(cfg.paths.features) / "classic_pair_features.parquet"
    if feat_path.exists():
        data = pd.read_parquet(feat_path)
    else:
        data = build_pair_features(
            pairs, lnc, mir, project_path(cfg.paths.features) / "accessibility"
        )
        data.to_parquet(feat_path, index=False)

    train = data[data.split == "train"]
    evals = data[data.split.isin(["val", "test"])].copy()
    tracking.setup(cfg)
    keep = ["pair_id", "gene_id", "mimat_id", "label", "split", "eval_group"]

    for name, cols in FEATURE_SETS.items():
        model = make_model(name, cfg.seed)
        model.fit(train[cols].to_numpy(), train.label.to_numpy())
        preds = evals[keep].copy()
        preds["score"] = model.predict_proba(evals[cols].to_numpy())[:, 1]
        table = evaluate(preds, n_boot=cfg.eval.n_boot, seed=cfg.seed)

        with mlflow.start_run(run_name=f"classic/{name}"):
            mlflow.set_tags({"family": "classic", "model": name})
            mlflow.log_params({"features": ",".join(cols), "estimator": type(model).__name__})
            tracking.log_results(
                table, preds, project_path(cfg.paths.predictions) / f"{name}.parquet"
            )

        row = table.set_index("group")
        print(
            f"{name:<18} cold_lncrna AUROC {row.at['test_cold_lncrna', 'auroc']:.3f} "
            f"AUPR {row.at['test_cold_lncrna', 'aupr']:.3f} | cold_both AUROC "
            f"{row.at['test_cold_both', 'auroc']:.3f} AUPR {row.at['test_cold_both', 'aupr']:.3f}"
        )
    rate = np.mean(evals[evals.eval_group == "cold_lncrna"].label)
    print(f"positive rate (test_cold_lncrna): {rate:.3f}")


if __name__ == "__main__":
    main()
