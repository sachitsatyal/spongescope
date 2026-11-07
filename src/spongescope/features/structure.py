"""MFE dot-bracket structures for the LncMiRPath baseline (paper used IPknot; we use
ViennaRNA RNA.fold per 200-nt segment, 50-nt overlap - same segmentation as the paper).

Outputs data/features/structure/lncrna_windows.parquet (transcript_id, window_idx, start,
structure) and mirna.parquet (mimat_id, structure).
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor

import hydra
import pandas as pd
from omegaconf import DictConfig
from tqdm import tqdm

from spongescope.features.common import (
    clean_rna,
    load_table,
    project_path,
    window_starts,
    write_manifest,
)


def fold(seq: str) -> str:
    import RNA

    return RNA.fold(seq)[0]


def _fold_transcript(tid: str, seq: str, seg: int, stride: int) -> list[tuple]:
    seq = clean_rna(seq)
    return [
        (tid, i, s, fold(seq[s : s + seg]))
        for i, s in enumerate(window_starts(len(seq), seg, stride))
    ]


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="features")
def main(cfg: DictConfig) -> None:
    sc = cfg.structure
    stride = sc.segment - sc.overlap
    out = project_path(cfg.paths.features) / "structure"
    out.mkdir(parents=True, exist_ok=True)
    lnc = load_table(cfg.paths.processed, "dim_lncrna")
    mir = load_table(cfg.paths.processed, "dim_mirna")

    t0 = time.time()
    rows: list[tuple] = []
    with ProcessPoolExecutor(max_workers=sc.workers) as pool:
        jobs = pool.map(
            _fold_transcript,
            lnc.transcript_id,
            lnc.sequence,
            [sc.segment] * len(lnc),
            [stride] * len(lnc),
            chunksize=8,
        )
        for r in tqdm(jobs, total=len(lnc), desc="fold lncRNA windows"):
            rows.extend(r)
    pd.DataFrame(rows, columns=["transcript_id", "window_idx", "start", "structure"]).to_parquet(
        out / "lncrna_windows.parquet", index=False
    )
    pd.DataFrame(
        {"mimat_id": mir.mimat_id, "structure": [fold(clean_rna(s)) for s in mir.sequence]}
    ).to_parquet(out / "mirna.parquet", index=False)

    write_manifest(
        out / "MANIFEST.json",
        {
            "tool": "ViennaRNA RNA.fold (MFE)",
            "segment": sc.segment,
            "overlap": sc.overlap,
            "n_windows": len(rows),
            "minutes": round((time.time() - t0) / 60, 1),
        },
    )
    print(f"{len(rows):,} windows folded in {(time.time() - t0) / 60:.1f} min -> {out}")


if __name__ == "__main__":
    main()
