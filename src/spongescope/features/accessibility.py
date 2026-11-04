"""Per-nucleotide target-site accessibility with ViennaRNA (RNAplfold algorithm).

For every lncRNA transcript, writes data/features/accessibility/<transcript_id>.npy,
float16 of shape (length, 2):
  col 0: probability the nucleotide is unpaired              (u = 1)
  col 1: probability the u-nt stretch ending here is unpaired (u = ulength, default 14)
Positions 1..ulength-1 (no full stretch yet) copy the first defined value.
Runs in parallel processes; re-running skips finished transcripts.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import hydra
import numpy as np
from omegaconf import DictConfig
from tqdm import tqdm

from spongescope.features.common import (
    clean_rna,
    load_table,
    project_path,
    write_manifest,
)


def _get(up, i: int, u: int) -> float:
    try:
        v = up[i][u]
        return float(v) if v is not None else float("nan")
    except (IndexError, TypeError):
        return float("nan")


def unpaired_profile(seq: str, window_size: int, max_bp_span: int, ulength: int) -> np.ndarray:
    import RNA

    n = len(seq)
    w = min(window_size, n)
    span = min(max_bp_span, w)
    up = RNA.pfl_fold_up(seq, ulength, w, span)  # up[i][u], 1-based i
    p1 = np.array([_get(up, i, 1) for i in range(1, n + 1)], dtype=np.float32)
    pu = np.array([_get(up, i, ulength) for i in range(1, n + 1)], dtype=np.float32)
    first = np.flatnonzero(~np.isnan(pu))
    if first.size:
        pu[: first[0]] = pu[first[0]]
    pu = np.nan_to_num(pu, nan=0.0)
    p1 = np.nan_to_num(p1, nan=0.0)
    return np.clip(np.stack([p1, pu], axis=1), 0.0, 1.0)


def _worker(tid: str, seq: str, out: str, w: int, span: int, u: int) -> tuple[str, int]:
    prof = unpaired_profile(clean_rna(seq), w, span, u)
    np.save(out, prof.astype(np.float16))
    return tid, len(seq)


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="features")
def main(cfg: DictConfig) -> None:
    ac = cfg.accessibility
    out_dir = project_path(cfg.paths.features) / "accessibility"
    out_dir.mkdir(parents=True, exist_ok=True)

    lnc = load_table(cfg.paths.processed, "dim_lncrna")
    todo = [
        (t, s)
        for t, s in zip(lnc.transcript_id, lnc.sequence, strict=True)
        if not (out_dir / f"{t}.npy").exists()
    ]
    todo.sort(key=lambda x: -len(x[1]))  # longest first keeps all workers busy
    print(f"{len(lnc):,} lncRNAs, {len(todo):,} to compute, {ac.workers} workers")

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=ac.workers) as pool:
        futures = [
            pool.submit(
                _worker,
                t,
                s,
                str(Path(out_dir) / f"{t}.npy"),
                ac.window_size,
                ac.max_bp_span,
                ac.ulength,
            )
            for t, s in todo
        ]
        for f in tqdm(as_completed(futures), total=len(futures), desc="accessibility"):
            f.result()

    write_manifest(
        out_dir / "MANIFEST.json",
        {
            "tool": "ViennaRNA RNA.pfl_fold_up (RNAplfold)",
            "window_size": ac.window_size,
            "max_bp_span": ac.max_bp_span,
            "ulength": ac.ulength,
            "columns": ["p_unpaired_1nt", f"p_unpaired_{ac.ulength}nt"],
            "n_lncrna": len(lnc),
            "minutes": round((time.time() - t0) / 60, 1),
        },
    )
    print(f"done in {(time.time() - t0) / 60:.1f} min -> {out_dir}")


if __name__ == "__main__":
    main()
