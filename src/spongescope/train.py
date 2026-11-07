"""Train a neural pair model on the cold-start splits, evaluate, log everything to MLflow.

uv run python -m spongescope.train                                   # LncMiRPath (seq+struct)
uv run python -m spongescope.train model.use_structure=false run_name=lncmirpath_seq_only
"""

from __future__ import annotations

from pathlib import Path

import hydra
import lightning as L
import numpy as np
import pandas as pd
import torch
from hydra.core.hydra_config import HydraConfig
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from lightning.pytorch.loggers import MLFlowLogger
from omegaconf import DictConfig, OmegaConf
from torch.utils.data import DataLoader

from spongescope import tracking
from spongescope.data.pairs import Collate, PairDataset, build_token_store
from spongescope.data.paper_style import paper_style_pairs
from spongescope.evaluation.metrics import evaluate, flatten
from spongescope.features.common import project_path
from spongescope.models.lncmirpath import LitPairModel


def loader(pairs: pd.DataFrame, store, cfg, shuffle: bool) -> DataLoader:
    return DataLoader(
        PairDataset(pairs),
        batch_size=cfg.data.batch_size,
        shuffle=shuffle,
        num_workers=cfg.data.num_workers,
        collate_fn=Collate(pairs.reset_index(drop=True), store),
    )


def warm_split(pairs: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Random 80/10/10 pair split inside train lncRNAs (lncRNAs shared across splits)."""
    d = pairs[pairs.split == "train"].copy()
    u = np.random.default_rng(seed).random(len(d))
    d["split"] = np.where(u < 0.8, "train", np.where(u < 0.9, "val", "test"))
    d["eval_group"] = np.where(d["split"] == "test", "warm", None)
    return d.reset_index(drop=True)


@hydra.main(version_base="1.3", config_path="../../configs", config_name="train")
def main(cfg: DictConfig) -> None:
    L.seed_everything(cfg.seed, workers=True)
    torch.set_float32_matmul_precision("high")
    proc, feat = project_path(cfg.paths.processed), project_path(cfg.paths.features)

    pairs = pd.read_parquet(proc / "fct_pairs.parquet")
    data_version = tracking.dataset_hash(proc / "fct_pairs.parquet")
    if cfg.data.warm_check and cfg.data.paper_style:
        raise ValueError("choose warm_check or paper_style, not both")
    if cfg.data.warm_check:
        pairs = warm_split(pairs, cfg.seed)
    if cfg.data.paper_style:
        pairs = paper_style_pairs(pairs, cfg.seed)
    store = build_token_store(proc, feat)
    train = pairs[pairs.split == "train"]
    val = pairs[pairs.split == "val"]
    evals = pairs[pairs.split.isin(["val", "test"])].reset_index(drop=True)
    print(f"train {len(train):,} | val {len(val):,} | val+test {len(evals):,}")

    model_cfg = OmegaConf.to_container(cfg.model, resolve=True)
    model = LitPairModel(model_cfg)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"model {cfg.model.name}: {n_params:,} parameters")

    mlf = MLFlowLogger(
        experiment_name=cfg.mlflow.experiment,
        tracking_uri=cfg.mlflow.tracking_uri,
        run_name=cfg.run_name,
        tags={
            "family": "neural",
            "model": cfg.model.name,
            "data_version": data_version,
            "warm_check": str(cfg.data.warm_check),
            "paper_style": str(cfg.data.paper_style),
        },
    )
    mlf.log_hyperparams(tracking.flat_params(cfg))
    ckpt_dir = Path(HydraConfig.get().runtime.output_dir) / "checkpoints"
    ckpt = ModelCheckpoint(
        dirpath=ckpt_dir, monitor="val/aupr", mode="max", save_top_k=1, filename="best"
    )
    trainer = L.Trainer(
        max_epochs=cfg.trainer.max_epochs,
        precision=cfg.trainer.precision,
        accelerator=cfg.trainer.accelerator,
        logger=mlf,
        callbacks=[
            ckpt,
            EarlyStopping(monitor="val/aupr", mode="max", patience=cfg.trainer.patience),
        ],
        log_every_n_steps=cfg.trainer.log_every_n_steps,
    )
    trainer.fit(model, loader(train, store, cfg, True), loader(val, store, cfg, False))

    best = LitPairModel.load_from_checkpoint(ckpt.best_model_path)
    scores = torch.cat(trainer.predict(best, loader(evals, store, cfg, False))).numpy()
    keep = ["pair_id", "gene_id", "mimat_id", "label", "split", "eval_group", "has_seed_site"]
    preds = evals[keep].copy()
    preds["score"] = scores
    table = evaluate(preds, n_boot=cfg.eval.n_boot, seed=cfg.seed)

    out = project_path(cfg.paths.predictions) / f"{cfg.run_name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(out, index=False)
    csv = out.with_suffix(".metrics.csv")
    table.to_csv(csv, index=False)
    for k, v in flatten(table).items():
        mlf.experiment.log_metric(mlf.run_id, k, v)
    mlf.experiment.log_artifact(mlf.run_id, str(out))
    mlf.experiment.log_artifact(mlf.run_id, str(csv))
    mlf.experiment.log_artifact(mlf.run_id, ckpt.best_model_path)

    cols = ["group", "n_pos", "n_neg", "auroc", "aupr", "aupr_lift", "per_lnc_auroc", "ece"]
    print(table[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
