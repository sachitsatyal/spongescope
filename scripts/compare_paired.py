"""Paired lncRNA-level bootstrap: is model A better than model B?

uv run python scripts\\compare_paired.py sitemil gbm_all
uv run python scripts\\compare_paired.py sitemil site_gbm --groups test_seed_controlled
"""

import argparse
from pathlib import Path

import pandas as pd

from spongescope.evaluation.compare import paired_bootstrap

PRED = Path(__file__).resolve().parents[1] / "data" / "predictions"
DEFAULT_GROUPS = ["test_cold_lncrna", "test_seed_controlled", "test_cold_both"]

ap = argparse.ArgumentParser()
ap.add_argument("model_a")
ap.add_argument("model_b")
ap.add_argument("--groups", nargs="+", default=DEFAULT_GROUPS)
ap.add_argument("--n-boot", type=int, default=2000)
args = ap.parse_args()

a = pd.read_parquet(PRED / f"{args.model_a}.parquet")
b = pd.read_parquet(PRED / f"{args.model_b}.parquet")
res = pd.concat([paired_bootstrap(a, b, g, args.n_boot) for g in args.groups])
res["significant"] = res.ci_lo > 0
print(f"A = {args.model_a}   B = {args.model_b}   (delta = A - B, 95% CI, paired by lncRNA)\n")
print(res.round(4).to_string(index=False))
