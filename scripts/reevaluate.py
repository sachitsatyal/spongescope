"""Recompute every data/predictions/*.metrics.csv from its saved predictions with the current
evaluation code (no retraining). Use after changing metric groups."""

from pathlib import Path

import pandas as pd

from spongescope.evaluation.metrics import evaluate

PRED = Path(__file__).resolve().parents[1] / "data" / "predictions"

for path in sorted(PRED.glob("*.parquet")):
    preds = pd.read_parquet(path)
    table = evaluate(preds, n_boot=1000, seed=42)
    table.to_csv(path.with_suffix(".metrics.csv"), index=False)
    print(f"{path.stem:<24} groups: {', '.join(table.group)}")
