"""Hand-crafted pair features for the classic baselines (no Hydra/MLflow; unit-testable)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from spongescope.features.seed_sites import pair_features

FEATURE_SETS = {
    # Shortcut checks: if these score well, the benchmark is learnable without biology.
    "length_only": ["log_len"],
    "mirna_popularity": ["mir_log_degree"],
    # Biology baseline: seed matches + accessibility (what TargetScan-style tools use).
    "seed_match": [
        "log_len",
        "gc",
        "n_8mer",
        "n_7mer_m8",
        "n_7mer_a1",
        "n_6mer",
        "dens_7mer_m8",
        "dens_6mer",
        "best_site_acc",
    ],
}
FEATURE_SETS["gbm_all"] = sorted({c for cols in FEATURE_SETS.values() for c in cols})


def build_pair_features(
    pairs: pd.DataFrame, lnc: pd.DataFrame, mir: pd.DataFrame, acc_dir: Path | None
) -> pd.DataFrame:
    """One row per pair with all classic features (pairs keeps its order)."""
    lnc = lnc.set_index("transcript_id")
    mir_seq = dict(zip(mir.mimat_id, mir.sequence, strict=True))
    train_pos = pairs[(pairs.split == "train") & (pairs.label == 1)]
    degree = train_pos.groupby("mimat_id").size()

    rows = []
    for tid, grp in tqdm(pairs.groupby("transcript_id", sort=False), desc="pair features"):
        seq = lnc.at[tid, "sequence"]
        acc = None
        if acc_dir is not None and (acc_dir / f"{tid}.npy").exists():
            acc = np.load(acc_dir / f"{tid}.npy")
        gc = (seq.count("G") + seq.count("C")) / len(seq)
        for idx, mid in zip(grp.index, grp.mimat_id, strict=True):
            f = pair_features(seq, mir_seq[mid], acc)
            f.update(
                {
                    "_row": idx,
                    "log_len": float(np.log10(len(seq))),
                    "gc": gc,
                    "mir_log_degree": float(np.log1p(degree.get(mid, 0))),
                }
            )
            rows.append(f)
    feats = pd.DataFrame(rows).set_index("_row").loc[pairs.index]
    return pd.concat([pairs.reset_index(drop=True), feats.reset_index(drop=True)], axis=1)
