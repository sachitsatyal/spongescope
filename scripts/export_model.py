"""Export a trained run to a self-contained model folder (safetensors + config.json).

  uv run python scripts\\export_model.py sitemil_s2
  uv run python scripts\\export_model.py sitemil_s2 --out models\\spongescope-v1

Temperature is refitted from the run's saved val logits, so the export is calibrated without
needing the training config. A golden input/output pair is recorded for the regression test.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import torch
import yaml
from safetensors.torch import save_file

from spongescope.evaluation.calibration import fit_temperature

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "data" / "predictions"


def _run_name_of(job_dir: Path) -> str | None:
    """Read the run_name from a Hydra job's saved config, resolving ${...} references.

    Hydra writes `run_name: sitemil_s${seed}` (sweep) or `${model.name}` (single run) into
    .hydra/config.yaml, with the referenced values in the same file.
    """
    cfg_path = job_dir / ".hydra" / "config.yaml"
    if not cfg_path.exists():
        return None
    raw = yaml.safe_load(cfg_path.read_text()) or {}
    name = str(raw.get("run_name", ""))
    for key, val in raw.items():
        if isinstance(val, dict):
            for sub, subval in val.items():
                name = name.replace(f"${{{key}.{sub}}}", str(subval))
        else:
            name = name.replace(f"${{{key}}}", str(val))
    return name or None


def candidate_checkpoints() -> list[tuple[Path, str | None]]:
    """Every best-checkpoint under outputs/ or multirun/, with the run_name that produced it.

    Hydra writes single runs to outputs/ (hydra.run.dir) but sweeps (-m) to multirun/, so both
    have to be searched; the job's .hydra/config.yaml is what says which run a checkpoint is.
    """
    found = [
        (ckpt, _run_name_of(ckpt.parent.parent))
        for root in ("outputs", "multirun")
        for ckpt in sorted((ROOT / root).glob("**/checkpoints/best*.ckpt"))
    ]
    return sorted(found, key=lambda t: t[0].stat().st_mtime)


def find_checkpoint(run_name: str) -> Path:
    cands = candidate_checkpoints()
    matches = [c for c, name in cands if name == run_name]
    if matches:
        return matches[-1]
    # fall back to the legacy layout, where the run name is in the path
    legacy = sorted(
        (ROOT / "outputs" / "train" / run_name).glob("*/checkpoints/best*.ckpt"),
        key=lambda p: p.stat().st_mtime,
    )
    if legacy:
        return legacy[-1]
    lines = [f"  {name or '?':<22} {c.relative_to(ROOT)}" for c, name in cands] or [
        "  (none found)"
    ]
    raise SystemExit(
        f"no checkpoint for run_name '{run_name}'. Checkpoints present:\n"
        + "\n".join(lines)
        + "\n\nPass one directly with --checkpoint <path>."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_name", nargs="?")
    ap.add_argument("--out", default=None)
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--list", action="store_true", help="list available checkpoints and exit")
    args = ap.parse_args()

    if args.list:
        for c, name in candidate_checkpoints():
            print(f"{name or '?':<22} {c.relative_to(ROOT)}")
        return
    if not args.run_name:
        raise SystemExit("run_name is required (or use --list to see what is available)")

    out = Path(args.out) if args.out else ROOT / "models" / "spongescope-v1"
    out.mkdir(parents=True, exist_ok=True)
    ckpt_path = Path(args.checkpoint) if args.checkpoint else find_checkpoint(args.run_name)
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    hp = ckpt["hyper_parameters"]
    model_cfg, dims = dict(hp["model_cfg"]), dict(hp["dims"])

    state = {
        k.removeprefix("net."): v.contiguous()
        for k, v in ckpt["state_dict"].items()
        if k.startswith("net.")
    }
    save_file(state, str(out / "model.safetensors"))

    preds = pd.read_parquet(PRED / f"{args.run_name}.parquet")
    if "logit" not in preds.columns:
        raise SystemExit(
            f"{args.run_name}.parquet has no 'logit' column; retrain with train_site.py"
        )
    val = preds[preds.split == "val"]
    temperature = fit_temperature(val.logit.to_numpy(), val.label.to_numpy())

    feat_cfg = yaml.safe_load((ROOT / "configs" / "features.yaml").read_text())
    metrics = pd.read_csv(PRED / f"{args.run_name}.metrics.csv").set_index("group")
    config = {
        "name": "spongescope",
        "run_name": args.run_name,
        "exported_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "checkpoint": str(ckpt_path.relative_to(ROOT)).replace("\\", "/"),
        "model": {k: v for k, v in model_cfg.items() if k not in ("lr", "weight_decay", "name")},
        "dims": dims,
        "temperature": temperature,
        "window": dims["window"],
        "max_sites": feat_cfg["sites"]["max_sites"],
        "au_window": feat_cfg["sites"]["au_window"],
        "accessibility": dict(feat_cfg["accessibility"]),
        "rnafm": {
            "layer": feat_cfg["rnafm"]["layer"],
            "window": feat_cfg["rnafm"]["window"],
            "stride": feat_cfg["rnafm"]["stride"],
        },
        "n_parameters": int(sum(v.numel() for v in state.values())),
        "metrics": {
            g: {m: float(metrics.at[g, m]) for m in ("auroc", "aupr", "per_lnc_auroc", "ece")}
            for g in metrics.index
        },
    }
    (out / "config.json").write_text(json.dumps(config, indent=2))

    # golden record: fixed input -> fixed output, so the test catches inference drift
    from spongescope.inference import SpongeScope

    model = SpongeScope.load(out)
    lnc = pd.read_parquet(ROOT / "data" / "processed" / "dim_lncrna.parquet")
    mir = pd.read_parquet(ROOT / "data" / "processed" / "dim_mirna.parquet")
    row = lnc.sort_values("transcript_id").iloc[0]
    mrow = mir.sort_values("mimat_id").iloc[0]
    kw = {}
    if config["model"]["use_rnafm"]:
        import numpy as np

        kw["lncrna_embedding"] = np.load(
            ROOT / "data" / "features" / "rnafm" / "lncrna" / f"{row.transcript_id}.npy"
        ).astype("float32")
        kw["mirna_embedding"] = np.load(ROOT / "data" / "features" / "rnafm" / "mirna.npz")[
            mrow.mimat_id
        ].astype("float32")
    p = model.predict(row.sequence, mrow.sequence, **kw)
    (out / "golden.json").write_text(
        json.dumps(
            {
                "transcript_id": row.transcript_id,
                "mimat_id": mrow.mimat_id,
                "probability": p.probability,
                "logit": p.logit,
                "n_candidate_sites": p.n_candidate_sites,
            },
            indent=2,
        )
    )

    print(f"exported -> {out}")
    print(f"  parameters   {config['n_parameters']:,}")
    print(f"  temperature  {temperature:.4f}")
    for g in ("test_cold_lncrna", "test_seed_controlled"):
        if g in config["metrics"]:
            m = config["metrics"][g]
            print(f"  {g:<22} AUROC {m['auroc']:.3f}  AUPR {m['aupr']:.3f}  ECE {m['ece']:.3f}")
    print(f"  golden       p={p.probability:.6f}  sites={p.n_candidate_sites}")


if __name__ == "__main__":
    main()
