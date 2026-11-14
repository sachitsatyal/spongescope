"""Combine several models' predictions into one, recalibrate on val, evaluate.

  uv run python scripts\\ensemble.py sitemil_s42 sitemil_s1 sitemil_s2 --out sitemil_ens3
  uv run python scripts\\ensemble.py sitemil_ens3 site_gbm --method rank --out sitemil_sitegbm

method mean: average the probabilities (right for runs of the same model, e.g. seeds).
method rank: average the within-group percentile ranks (right for mixing different model
families, whose scores are on different scales).
Temperature is refitted on val so the ensemble stays calibrated.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from spongescope.evaluation.calibration import apply_temperature, fit_temperature
from spongescope.evaluation.metrics import evaluate

PRED = Path(__file__).resolve().parents[1] / "data" / "predictions"
KEY = ["pair_id", "gene_id", "mimat_id", "label", "split", "eval_group", "has_seed_site"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--method", choices=["mean", "rank"], default="mean")
    ap.add_argument("--n-boot", type=int, default=1000)
    args = ap.parse_args()

    frames = []
    for name in args.models:
        d = pd.read_parquet(PRED / f"{name}.parquet").set_index("pair_id")
        frames.append(d["score"].rank(pct=True) if args.method == "rank" else d["score"])
    base = pd.read_parquet(PRED / f"{args.models[0]}.parquet").set_index("pair_id")
    for name, f in zip(args.models[1:], frames[1:], strict=True):
        if not f.index.equals(frames[0].index):
            raise ValueError(f"{name} scores a different set of pairs than {args.models[0]}")

    combined = pd.concat(frames, axis=1).mean(axis=1).clip(1e-6, 1 - 1e-6)
    out = base[KEY[1:]].copy()
    out["logit"] = np.log(combined / (1 - combined))

    is_val = (out.split == "val").to_numpy()
    t = fit_temperature(out.logit.to_numpy()[is_val], out.label.to_numpy()[is_val])
    out["score"] = apply_temperature(out.logit.to_numpy(), t)
    out = out.reset_index()

    table = evaluate(out, n_boot=args.n_boot)
    out.to_parquet(PRED / f"{args.out}.parquet", index=False)
    table.to_csv(PRED / f"{args.out}.metrics.csv", index=False)
    print(f"{args.out}  <-  {', '.join(args.models)}  (method {args.method}, T={t:.3f})")
    print(table[["group", "auroc", "aupr", "per_lnc_auroc", "ece"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
