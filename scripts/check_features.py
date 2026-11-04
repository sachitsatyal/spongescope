"""Check that every lncRNA/miRNA has features with the right shape and sane values."""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
FEAT = ROOT / "data" / "features"

lnc = pd.read_parquet(PROC / "dim_lncrna.parquet")
mir = pd.read_parquet(PROC / "dim_mirna.parquet")

problems = []
emb_bytes = acc_bytes = 0
acc_means = []
for tid, n in zip(lnc.transcript_id, lnc.transcript_length, strict=True):
    e = FEAT / "rnafm" / "lncrna" / f"{tid}.npy"
    a = FEAT / "accessibility" / f"{tid}.npy"
    if not e.exists():
        problems.append(f"missing embedding {tid}")
    else:
        emb_bytes += e.stat().st_size
        arr = np.load(e, mmap_mode="r")
        if arr.shape != (n, 640):
            problems.append(f"embedding shape {tid}: {arr.shape} != ({n}, 640)")
    if not a.exists():
        problems.append(f"missing accessibility {tid}")
    else:
        acc_bytes += a.stat().st_size
        arr = np.load(a).astype(np.float32)
        if arr.shape != (n, 2):
            problems.append(f"accessibility shape {tid}: {arr.shape} != ({n}, 2)")
        elif np.isnan(arr).any() or arr.min() < 0 or arr.max() > 1:
            problems.append(f"accessibility values out of range {tid}")
        else:
            acc_means.append(arr.mean(0))

mz = FEAT / "rnafm" / "mirna.npz"
if mz.exists():
    m = np.load(mz)
    missing = set(mir.mimat_id) - set(m.files)
    if missing:
        problems.append(f"{len(missing)} miRNAs missing embeddings")
else:
    problems.append("mirna.npz missing")

print(f"lncRNAs checked:            {len(lnc):,}")
print(f"embedding files:            {emb_bytes / 1e9:.2f} GB")
print(f"accessibility files:        {acc_bytes / 1e6:.1f} MB")
if acc_means:
    mm = np.mean(acc_means, 0)
    print(f"mean P(unpaired) 1nt / 14nt: {mm[0]:.3f} / {mm[1]:.3f}")
print(f"problems:                   {len(problems)}")
for p in problems[:20]:
    print("  -", p)
