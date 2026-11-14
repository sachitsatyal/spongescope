"""Latency gate: time one prediction on CPU.

  uv run python scripts\\bench_latency.py
  uv run python scripts\\bench_latency.py --n 50 --model models\\spongescope-v1

Reports three paths separately, because they have very different costs:
  cached      lncRNA RNA-FM embedding + accessibility already on disk (the gate: < 1 s)
  accessibility   ViennaRNA on the transcript (needed for a pasted sequence)
  rnafm       RNA-FM forward on the transcript (the expensive part of a pasted sequence)
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from spongescope.inference import SpongeScope, accessibility_profile

ROOT = Path(__file__).resolve().parents[1]


def quantiles(xs: list[float]) -> str:
    a = np.array(xs) * 1000
    return f"p50 {np.percentile(a, 50):7.1f} ms   p95 {np.percentile(a, 95):7.1f} ms   n={len(a)}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "models" / "spongescope-v1"))
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()

    torch.set_num_threads(max(1, (torch.get_num_threads() or 4) // 2))
    model = SpongeScope.load(args.model, device="cpu")
    lnc = pd.read_parquet(ROOT / "data" / "processed" / "dim_lncrna.parquet")
    mir = pd.read_parquet(ROOT / "data" / "processed" / "dim_mirna.parquet")
    rows = lnc.sample(min(args.n, len(lnc)), random_state=0).reset_index(drop=True)
    mirs = mir.sample(len(rows), random_state=0, replace=len(mir) < len(rows)).reset_index(
        drop=True
    )
    mz = np.load(ROOT / "data" / "features" / "rnafm" / "mirna.npz") if model.use_rnafm else None

    cached, acc_only = [], []
    for i in range(len(rows)):
        r, m = rows.iloc[i], mirs.iloc[i]
        acc = np.load(
            ROOT / "data" / "features" / "accessibility" / f"{r.transcript_id}.npy"
        ).astype("float32")
        kw = {"accessibility": acc}
        if model.use_rnafm:
            kw["lncrna_embedding"] = np.load(
                ROOT / "data" / "features" / "rnafm" / "lncrna" / f"{r.transcript_id}.npy"
            ).astype("float32")
            kw["mirna_embedding"] = mz[m.mimat_id].astype("float32")
        model.predict(r.sequence, m.sequence, **kw)  # warm up caches/threads
        t0 = time.perf_counter()
        model.predict(r.sequence, m.sequence, **kw)
        cached.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        accessibility_profile(r.sequence, model.config)
        acc_only.append(time.perf_counter() - t0)

    print(
        f"transcript length: median {int(rows.transcript_length.median()):,} nt, "
        f"max {int(rows.transcript_length.max()):,} nt"
    )
    print(f"cached pair        {quantiles(cached)}   <- GATE: p95 < 1000 ms")
    print(f"accessibility      {quantiles(acc_only)}")

    if model.use_rnafm:
        try:
            import fm

            net, alphabet = fm.pretrained.rna_fm_t12()
            net.eval()
            conv = alphabet.get_batch_converter()
            rnafm = []
            for i in range(min(5, len(rows))):
                seq = rows.iloc[i].sequence[:1000]
                t0 = time.perf_counter()
                with torch.no_grad():
                    _, _, toks = conv([("x", seq)])
                    net(toks, repr_layers=[12])
                rnafm.append(time.perf_counter() - t0)
            print(f"rnafm 1000-nt win  {quantiles(rnafm)}  (x ceil(len/500) windows per new seq)")
        except (ImportError, OSError, RuntimeError, ValueError) as e:
            print(f"rnafm timing skipped: {type(e).__name__}: {e}")
    print("\nfor a pasted (uncached) sequence add accessibility + rnafm to the cached time")


if __name__ == "__main__":
    main()
