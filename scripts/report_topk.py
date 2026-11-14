"""Practical usefulness: if a lab tests the top-k ranked miRNAs for a lncRNA, how many are real?

AUPR averages precision over the whole recall curve, including the deep tail nobody screens.
Screening only ever uses the top of the ranking, so this reports precision@k per lncRNA.

  uv run python scripts\\report_topk.py
  uv run python scripts\\report_topk.py --group test_seed_controlled
  uv run python scripts\\report_topk.py --models sitemil_s42 site_gbm gbm_all
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from spongescope.evaluation.metrics import GROUPS

PRED = Path(__file__).resolve().parents[1] / "data" / "predictions"
KS = (1, 5, 10, 20)


def per_lncrna_topk(d: pd.DataFrame, ks=KS) -> dict[str, float]:
    """Mean precision@k and recall@k over lncRNAs with >=1 positive and >=k candidates."""
    out: dict[str, float] = {}
    counted = 0
    for k in ks:
        precs, recs = [], []
        for _, g in d.groupby("gene_id"):
            if g.label.sum() == 0 or len(g) < k:
                continue
            top = g.nlargest(k, "score")
            precs.append(top.label.mean())
            recs.append(top.label.sum() / g.label.sum())
        out[f"p@{k}"] = float(np.mean(precs)) if precs else float("nan")
        out[f"r@{k}"] = float(np.mean(recs)) if recs else float("nan")
        counted = max(counted, len(precs))
    out["n_lncrna"] = counted
    return out


def global_topfrac(d: pd.DataFrame, fracs=(0.01, 0.05)) -> dict[str, float]:
    """Precision in the top fraction of ALL pairs (one global ranking, screening-wide)."""
    s = d.sort_values("score", ascending=False)
    return {
        f"top{int(f * 100)}%": float(s.head(max(int(len(s) * f), 1)).label.mean()) for f in fracs
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=None)
    ap.add_argument("--group", default="test_cold_lncrna", choices=sorted(GROUPS))
    args = ap.parse_args()

    names = args.models or sorted(p.stem for p in PRED.glob("*.parquet"))
    if not names:
        raise SystemExit(f"no prediction files in {PRED}")

    rows, skipped = [], []
    for name in names:
        path = PRED / f"{name}.parquet"
        if not path.exists():
            skipped.append(f"{name} (no file)")
            continue
        d = pd.read_parquet(path)
        d = d[GROUPS[args.group](d)]
        if d.empty or d.label.nunique() < 2:
            skipped.append(f"{name} (not scored on this group)")
            continue
        rows.append(
            {
                "model": name,
                "base_rate": d.label.mean(),
                **per_lncrna_topk(d),
                **global_topfrac(d),
            }
        )

    if not rows:
        raise SystemExit(f"no model has predictions for group '{args.group}'. Skipped: {skipped}")

    t = pd.DataFrame(rows).sort_values("p@10", ascending=False)
    base = t.base_rate.iloc[0]
    print(f"group: {args.group}   base rate (random guessing): {base:.3f}")
    print(f"lncRNAs counted: {int(t.n_lncrna.max())}\n")
    print(
        t[["model", "p@1", "p@5", "p@10", "p@20", "r@10", "top1%", "top5%"]]
        .round(3)
        .to_string(index=False)
    )
    lift = (t.set_index("model")["p@10"] / base).round(2)
    print(f"\np@10 lift over random:\n{lift.to_string()}")
    if skipped:
        print(f"\nskipped: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
