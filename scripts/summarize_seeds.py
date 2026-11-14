"""Mean +/- sd across runs whose name starts with a prefix, e.g. the 3 seeds of sitemil.

uv run python scripts\\summarize_seeds.py sitemil_s
"""

import sys
from pathlib import Path

import pandas as pd

from spongescope.evaluation.compare import seed_summary

PRED = Path(__file__).resolve().parents[1] / "data" / "predictions"
prefix = sys.argv[1] if len(sys.argv) > 1 else "sitemil_s"
files = sorted(PRED.glob(f"{prefix}*.metrics.csv"))
if not files:
    raise SystemExit(f"no {prefix}*.metrics.csv in {PRED}")
tables = {f.name.removesuffix(".metrics.csv"): pd.read_csv(f) for f in files}
print("runs:", ", ".join(tables))
print(seed_summary(tables).round(4).to_string(index=False))
