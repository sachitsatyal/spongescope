"""Candidate-site tables for every pair in fct_pairs (input of SpongeScope + site_gbm).

data/features/sites/sites.parquet  one row per kept site (max_sites per pair, strongest first)
data/features/sites/pairs.parquet  one row per pair: site counts by type (before the cap)
"""

from __future__ import annotations

import time
from pathlib import Path

import hydra
import numpy as np
import pandas as pd
from omegaconf import DictConfig
from tqdm import tqdm

from spongescope.features.common import clean_rna, load_table, project_path, write_manifest
from spongescope.features.site_scan import N_TYPES, SITE_TYPES, encode, scan

SITE_COLS = [
    "pair_id",
    "p2",
    "type_id",
    "wc2",
    "wc3",
    "wc4",
    "wc5",
    "wc6",
    "wc7",
    "wc8",
    "n_wobble",
    "a1",
    "supp",
    "rel_pos",
    "end_dist",
    "au_local",
    "acc_site",
    "acc_u14",
]
COUNT_COLS = [f"n_{t}" for t in SITE_TYPES]
# columns that must be integers wherever a site table is built (training AND serving)
INT_SITE_COLS = [
    "p2",
    "type_id",
    "wc2",
    "wc3",
    "wc4",
    "wc5",
    "wc6",
    "wc7",
    "wc8",
    "n_wobble",
    "a1",
    "supp",
]


def site_rows(
    target: np.ndarray,
    mirna: np.ndarray,
    acc: np.ndarray | None,
    au_cum: np.ndarray,
    max_sites: int,
    au_window: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Features of the kept sites (k, 17) sorted by p2, and counts by type (N_TYPES,)."""
    s = scan(target, mirna)
    counts = np.bincount(s.type_id, minlength=N_TYPES) if len(s) else np.zeros(N_TYPES, int)
    if not len(s):
        return np.zeros((0, len(SITE_COLS) - 1)), counts
    n = len(target)
    lo = np.clip(s.p2 - au_window, 0, n)
    hi = np.clip(s.p2 + au_window + 1, 0, n)
    au_local = (au_cum[hi] - au_cum[lo]) / np.maximum(hi - lo, 1)
    if acc is not None:
        p1 = acc[:, 0].astype(np.float32)
        p1_cum = np.concatenate([[0.0], np.cumsum(p1)])
        a, b = np.clip(s.p2 - 6, 0, n), np.clip(s.p2 + 2, 0, n)  # site span incl. A1
        acc_site = (p1_cum[b] - p1_cum[a]) / np.maximum(b - a, 1)
        acc_u14 = acc[np.minimum(s.p2 + 1, n - 1), 1].astype(np.float32)
    else:
        acc_site = acc_u14 = np.zeros(len(s), np.float32)

    order = np.lexsort((-acc_site, s.type_id))[:max_sites]  # strongest type, then most open
    order = order[np.argsort(s.p2[order])]
    feats = np.column_stack(
        [
            s.p2,
            s.type_id,
            s.wc.astype(np.int8),
            s.n_wobble,
            s.a1.astype(np.int8),
            s.supp,
            s.p2 / n,
            np.log1p(np.minimum(s.p2, n - 1 - s.p2)) / 10,
            au_local,
            acc_site,
            acc_u14,
        ]
    )[order]
    return feats, counts


def build_site_tables(
    pairs: pd.DataFrame,
    lnc: pd.DataFrame,
    mir: pd.DataFrame,
    acc_dir: Path | None,
    max_sites: int = 16,
    au_window: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    seqs = dict(zip(lnc.transcript_id, lnc.sequence, strict=True))
    mir_codes = {m: encode(clean_rna(s)) for m, s in zip(mir.mimat_id, mir.sequence, strict=True)}
    site_blocks, site_ids, pair_rows = [], [], []
    for tid, grp in tqdm(pairs.groupby("transcript_id", sort=False), desc="scan sites"):
        target = encode(clean_rna(seqs[tid]))
        is_au = (target == 0) | (target == 3)
        au_cum = np.concatenate([[0], np.cumsum(is_au)])
        acc = None
        if acc_dir is not None and (acc_dir / f"{tid}.npy").exists():
            acc = np.load(acc_dir / f"{tid}.npy")
        for pid, mid in zip(grp.pair_id, grp.mimat_id, strict=True):
            feats, counts = site_rows(target, mir_codes[mid], acc, au_cum, max_sites, au_window)
            if len(feats):
                site_blocks.append(feats)
                site_ids.extend([pid] * len(feats))
            pair_rows.append(
                (pid, int(counts.sum()), len(feats), *counts.tolist(), float(np.log10(len(target))))
            )
    block = np.vstack(site_blocks) if site_blocks else np.zeros((0, len(SITE_COLS) - 1))
    sites = pd.DataFrame(block, columns=SITE_COLS[1:])
    sites.insert(0, "pair_id", site_ids)
    sites[INT_SITE_COLS] = sites[INT_SITE_COLS].astype(np.int64)
    pair_tab = pd.DataFrame(
        pair_rows, columns=["pair_id", "n_sites", "n_kept", *COUNT_COLS, "log_len"]
    )
    return sites, pair_tab


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="features")
def main(cfg: DictConfig) -> None:
    sc = cfg.sites
    pairs = load_table(cfg.paths.processed, "fct_pairs")
    lnc = load_table(cfg.paths.processed, "dim_lncrna")
    mir = load_table(cfg.paths.processed, "dim_mirna")
    feat = project_path(cfg.paths.features)
    out = feat / "sites"
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    sites, pair_tab = build_site_tables(
        pairs, lnc, mir, feat / "accessibility", sc.max_sites, sc.au_window
    )
    sites.to_parquet(out / "sites.parquet", index=False)
    pair_tab.to_parquet(out / "pairs.parquet", index=False)
    write_manifest(
        out / "MANIFEST.json",
        {
            "site_types": list(SITE_TYPES),
            "max_sites": sc.max_sites,
            "au_window": sc.au_window,
            "n_pairs": len(pair_tab),
            "n_sites_kept": len(sites),
            "minutes": round((time.time() - t0) / 60, 1),
        },
    )
    print(f"{len(sites):,} sites for {len(pair_tab):,} pairs in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
