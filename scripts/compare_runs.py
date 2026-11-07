"""Benchmark table from every data/predictions/*.parquet -> reports/benchmark.md."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "data" / "predictions"
OUT = ROOT / "reports" / "benchmark.md"

GROUP_ORDER = ["test_cold_lncrna", "test_cold_both", "val"]

rows = []
for csv in sorted(PRED.glob("*.metrics.csv")):
    t = pd.read_csv(csv)
    t.insert(0, "model", csv.name.removesuffix(".metrics.csv"))
    rows.append(t)
if not rows:
    raise SystemExit(f"no *.metrics.csv files in {PRED}")
df = pd.concat(rows)


def fmt(r, m):
    return f"{r[m]:.3f} [{r[m + '_lo']:.3f}-{r[m + '_hi']:.3f}]"


lines = ["# SpongeScope benchmark (cold-start splits)", ""]
lines += [
    "AUROC / AUPR with 95% CI from a lncRNA-level bootstrap. `lift` = AUPR / positive rate.",
    "`per-lnc AUROC` = mean AUROC within each lncRNA (ignores length/hub shortcuts).",
    "",
]
for g in GROUP_ORDER:
    d = df[df.group == g].sort_values("aupr", ascending=False)
    if d.empty:
        continue
    r0 = d.iloc[0]
    lines += [
        f"## {g}  (pos {int(r0.n_pos):,} / neg {int(r0.n_neg):,}, positive rate {r0.pos_rate:.3f})",
        "",
    ]
    lines += ["| model | AUROC | AUPR | lift | per-lnc AUROC | ECE |", "|---|---|---|---|---|---|"]
    for _, r in d.iterrows():
        lines.append(
            f"| {r.model} | {fmt(r, 'auroc')} | {fmt(r, 'aupr')} | {r.aupr_lift:.2f} | "
            f"{r.per_lnc_auroc:.3f} | {r.ece:.3f} |"
        )
    lines.append("")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print(f"\nwritten: {OUT}")
