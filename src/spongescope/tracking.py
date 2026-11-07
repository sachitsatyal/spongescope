"""Small MLflow helpers shared by baselines and neural training."""

from __future__ import annotations

from pathlib import Path

import mlflow
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from spongescope.evaluation.metrics import flatten


def flat_params(cfg: DictConfig) -> dict[str, str]:
    cont = OmegaConf.to_container(cfg, resolve=True)
    cont.pop("hydra", None)
    out: dict[str, str] = {}

    def walk(prefix: str, node) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(f"{prefix}.{k}" if prefix else str(k), v)
        else:
            out[prefix] = str(node)[:500]

    walk("", cont)
    return out


def setup(cfg: DictConfig) -> None:
    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment)


def log_results(table: pd.DataFrame, preds: pd.DataFrame, out_path: Path) -> None:
    """Inside an active run: metrics, metric table and predictions as artifacts."""
    mlflow.log_metrics(flatten(table))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(out_path, index=False)
    csv = out_path.with_suffix(".metrics.csv")
    table.to_csv(csv, index=False)
    mlflow.log_artifact(str(out_path))
    mlflow.log_artifact(str(csv))
