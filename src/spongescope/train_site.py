"""Train the SpongeScope site model, calibrate it, evaluate, log to MLflow.

uv run python -m spongescope.train_site
uv run python -m spongescope.train_site model.use_rnafm=false run_name=sitemil_no_rnafm
uv run python -m spongescope.train_site model.use_accessibility=false run_name=sitemil_no_acc
uv run python -m spongescope.train_site model.use_cross_attention=false run_name=sitemil_no_xattn
"""

from __future__ import annotations

from pathlib import Path

import hydra
import lightning as L
import pandas as pd
import torch
from hydra.core.hydra_config import HydraConfig
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from lightning.pytorch.loggers import MLFlowLogger
from omegaconf import DictConfig, OmegaConf
from torch.utils.data import DataLoader

from spongescope import tracking
from spongescope.data.site_data import (
    PAIR_FEAT_DIM,
    SITE_FEAT_DIM,
    PairIndex,
    SiteCollate,
    load_site_store,
)
from spongescope.evaluation.calibration import apply_temperature, fit_temperature
from spongescope.evaluation.metrics import evaluate, flatten
from spongescope.features.common import project_path
from spongescope.models.sitemil import LitSiteModel


def loader(pairs: pd.DataFrame, store, cfg, shuffle: bool) -> DataLoader:
    pairs = pairs.reset_index(drop=True)
    return DataLoader(
        PairIndex(len(pairs)),
        batch_size=cfg.data.batch_size,
        shuffle=shuffle,
        num_workers=cfg.data.num_workers,
        collate_fn=SiteCollate(pairs, store),
    )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="train_site")
def main(cfg: DictConfig) -> None:
    L.seed_everything(cfg.seed, workers=True)
    torch.set_float32_matmul_precision("high")
    proc, feat = project_path(cfg.paths.processed), project_path(cfg.paths.features)
    pairs = pd.read_parquet(proc / "fct_pairs.parquet")
    data_version = tracking.dataset_hash(proc / "fct_pairs.parquet")
    store = load_site_store(
        proc,
        feat,
        use_rnafm=cfg.model.use_rnafm,
        use_accessibility=cfg.model.use_accessibility,
        window=cfg.data.window,
        max_sites=cfg.data.max_sites,
    )
    train, val = pairs[pairs.split == "train"], pairs[pairs.split == "val"]
    evals = pairs[pairs.split.isin(["val", "test"])].reset_index(drop=True)
    print(f"train {len(train):,} | val {len(val):,} | val+test {len(evals):,}")

    dims = {
        "tok_dim": store.tok_dim,
        "mir_dim": store.mir_dim,
        "site_feat_dim": SITE_FEAT_DIM,
        "pair_feat_dim": PAIR_FEAT_DIM,
        "window": cfg.data.window,
    }
    model = LitSiteModel(OmegaConf.to_container(cfg.model, resolve=True), dims)
    print(f"model {cfg.model.name}: {sum(p.numel() for p in model.parameters()):,} parameters")

    mlf = MLFlowLogger(
        experiment_name=cfg.mlflow.experiment,
        tracking_uri=cfg.mlflow.tracking_uri,
        run_name=cfg.run_name,
        tags={"family": "neural", "model": cfg.model.name, "data_version": data_version},
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
        gradient_clip_val=cfg.trainer.gradient_clip_val,
        logger=mlf,
        callbacks=[
            ckpt,
            EarlyStopping(monitor="val/aupr", mode="max", patience=cfg.trainer.patience),
        ],
        log_every_n_steps=cfg.trainer.log_every_n_steps,
    )
    trainer.fit(model, loader(train, store, cfg, True), loader(val, store, cfg, False))

    best = LitSiteModel.load_from_checkpoint(ckpt.best_model_path)
    logits = torch.cat(trainer.predict(best, loader(evals, store, cfg, False))).numpy()
    is_val = (evals.split == "val").to_numpy()
    temperature = fit_temperature(logits[is_val], evals.label.to_numpy()[is_val])

    keep = ["pair_id", "gene_id", "mimat_id", "label", "split", "eval_group", "has_seed_site"]
    preds = evals[keep].copy()
    preds["logit"] = logits
    preds["score"] = apply_temperature(logits, temperature)
    table = evaluate(preds, n_boot=cfg.eval.n_boot, seed=cfg.seed)

    out = project_path(cfg.paths.predictions) / f"{cfg.run_name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(out, index=False)
    csv = out.with_suffix(".metrics.csv")
    table.to_csv(csv, index=False)
    for k, v in {**flatten(table), "temperature": temperature}.items():
        mlf.experiment.log_metric(mlf.run_id, k, v)
    for path in (out, csv, ckpt.best_model_path):
        mlf.experiment.log_artifact(mlf.run_id, str(path))

    print(f"temperature: {temperature:.3f}")
    cols = ["group", "n_pos", "n_neg", "auroc", "aupr", "aupr_lift", "per_lnc_auroc", "ece"]
    print(table[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
