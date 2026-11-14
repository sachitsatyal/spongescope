"""Batches for the SpongeScope site model.

Per pair: up to max_sites candidate sites. Each site = a (2*window+1)-nt lncRNA window centred
on p2 (RNA-FM embedding + accessibility, or one-hot when RNA-FM is ablated) + 21 site features.
The miRNA is given as per-nucleotide tokens. torch is imported lazily so the numpy side is
testable without it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from spongescope.features.common import clean_rna
from spongescope.features.site_scan import N_TYPES, encode

SITE_FEAT_DIM = N_TYPES + 7 + 8  # type one-hot, wc2..wc8, 8 scalars
PAIR_FEAT_DIM = N_TYPES + 3  # log1p counts by type, log1p total, has_site, log_len


def one_hot(codes: np.ndarray) -> np.ndarray:
    out = np.zeros((len(codes), 4), dtype=np.float16)
    ok = codes < 4
    out[np.flatnonzero(ok), codes[ok]] = 1
    return out


def site_matrix(sites: pd.DataFrame, use_accessibility: bool) -> np.ndarray:
    t = sites["type_id"].to_numpy()
    m = np.zeros((len(sites), SITE_FEAT_DIM), dtype=np.float32)
    m[np.arange(len(sites)), t] = 1
    m[:, N_TYPES : N_TYPES + 7] = sites[
        ["wc2", "wc3", "wc4", "wc5", "wc6", "wc7", "wc8"]
    ].to_numpy()
    scal = np.column_stack(
        [
            sites["n_wobble"] / 2,
            sites["a1"],
            sites["supp"] / 4,
            sites["rel_pos"],
            sites["end_dist"],
            sites["au_local"],
            sites["acc_site"] * use_accessibility,
            sites["acc_u14"] * use_accessibility,
        ]
    )
    m[:, N_TYPES + 7 :] = scal
    return m


def pair_matrix(pair_tab: pd.DataFrame) -> np.ndarray:
    counts = pair_tab[
        [c for c in pair_tab.columns if c.startswith("n_") and c not in ("n_sites", "n_kept")]
    ].to_numpy()
    return np.column_stack(
        [
            np.log1p(counts),
            np.log1p(pair_tab["n_sites"]),
            (pair_tab["n_sites"] > 0).astype(float),
            pair_tab["log_len"],
        ]
    ).astype(np.float32)


class SiteStore:
    """All per-pair site data + lazy access to lncRNA token features."""

    def __init__(
        self,
        lnc: pd.DataFrame,
        mir: pd.DataFrame,
        sites: pd.DataFrame,
        pair_tab: pd.DataFrame,
        features: Path,
        use_rnafm: bool = True,
        use_accessibility: bool = True,
        window: int = 40,
        max_sites: int = 16,
        max_mir_len: int = 40,
    ):
        self.features, self.window, self.max_sites = Path(features), window, max_sites
        self.use_rnafm, self.use_accessibility = use_rnafm, use_accessibility
        self.T = 2 * window + 1
        self.emb_dim = 640 if use_rnafm else 4
        self.tok_dim = self.emb_dim + (2 if use_accessibility else 0)
        self.mir_dim = 640 if use_rnafm else 4
        self.length = dict(zip(lnc.transcript_id, lnc.transcript_length, strict=True))

        sites = sites.sort_values(["pair_id", "p2"], kind="stable").reset_index(drop=True)
        mat = site_matrix(sites, use_accessibility)
        pid = sites["pair_id"].to_numpy()
        cuts = np.flatnonzero(pid[1:] != pid[:-1]) + 1
        starts = np.concatenate([[0], cuts]) if len(pid) else np.array([], int)
        ends = np.concatenate([cuts, [len(pid)]]) if len(pid) else np.array([], int)
        p2 = sites["p2"].to_numpy()
        self.site_p2 = {pid[s]: p2[s:e] for s, e in zip(starts, ends, strict=True)}
        self.site_feat = {pid[s]: mat[s:e] for s, e in zip(starts, ends, strict=True)}
        self.pair_feat = dict(zip(pair_tab["pair_id"], pair_matrix(pair_tab), strict=True))

        self._emb: dict[str, np.ndarray] = {}
        self._codes = {}
        if not use_rnafm:
            self._codes = {
                t: encode(clean_rna(s))
                for t, s in zip(lnc.transcript_id, lnc.sequence, strict=True)
            }
        self._acc: dict[str, np.ndarray] = {}
        if use_rnafm:
            mz = np.load(self.features / "rnafm" / "mirna.npz")
            self.mir_tok = {m: mz[m][:max_mir_len] for m in mz.files}
        else:
            self.mir_tok = {
                m: one_hot(encode(clean_rna(s)))[:max_mir_len]
                for m, s in zip(mir.mimat_id, mir.sequence, strict=True)
            }

    def _lnc_emb(self, tid: str) -> np.ndarray:
        if self.use_rnafm:
            if tid not in self._emb:
                path = self.features / "rnafm" / "lncrna" / f"{tid}.npy"
                self._emb[tid] = np.load(path, mmap_mode="r")
            return self._emb[tid]
        return one_hot(self._codes[tid])

    def _lnc_acc(self, tid: str) -> np.ndarray:
        if tid not in self._acc:
            self._acc[tid] = np.load(self.features / "accessibility" / f"{tid}.npy")
        return self._acc[tid]

    def window_tokens(self, tid: str, p2: int) -> tuple[np.ndarray, np.ndarray]:
        n, w = self.length[tid], self.window
        lo, hi = p2 - w, p2 + w + 1
        a, b = max(lo, 0), min(hi, n)
        tok = np.zeros((self.T, self.tok_dim), dtype=np.float16)
        mask = np.zeros(self.T, dtype=bool)
        tok[a - lo : b - lo, : self.emb_dim] = self._lnc_emb(tid)[a:b]
        if self.use_accessibility:
            tok[a - lo : b - lo, self.emb_dim :] = self._lnc_acc(tid)[a:b]
        mask[a - lo : b - lo] = True
        return tok, mask


def load_site_store(processed: Path, features: Path, **kw) -> SiteStore:
    return SiteStore(
        pd.read_parquet(processed / "dim_lncrna.parquet"),
        pd.read_parquet(processed / "dim_mirna.parquet"),
        pd.read_parquet(features / "sites" / "sites.parquet"),
        pd.read_parquet(features / "sites" / "pairs.parquet"),
        features,
        **kw,
    )


class PairIndex:
    """Map-style dataset of row positions (works with torch DataLoader)."""

    def __init__(self, n: int):
        self.n = n

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, i: int) -> int:
        return i


class SiteCollate:
    def __init__(self, pairs: pd.DataFrame, store: SiteStore):
        self.pids = pairs["pair_id"].to_numpy()
        self.tids = pairs["transcript_id"].to_numpy()
        self.mids = pairs["mimat_id"].to_numpy()
        self.labels = pairs["label"].to_numpy().astype(np.float32)
        self.store = store

    def numpy_batch(self, idx) -> dict[str, np.ndarray]:
        st, idx = self.store, np.asarray(idx)
        b = len(idx)
        n_sites = [min(len(st.site_p2.get(self.pids[i], ())), st.max_sites) for i in idx]
        s = max(max(n_sites), 1)
        site_tok = np.zeros((b, s, st.T, st.tok_dim), dtype=np.float16)
        tok_mask = np.zeros((b, s, st.T), dtype=bool)
        site_feat = np.zeros((b, s, SITE_FEAT_DIM), dtype=np.float32)
        site_mask = np.zeros((b, s), dtype=bool)
        pair_feat = np.zeros((b, PAIR_FEAT_DIM), dtype=np.float32)
        for r, (i, k) in enumerate(zip(idx, n_sites, strict=True)):
            pid, tid = self.pids[i], self.tids[i]
            pair_feat[r] = st.pair_feat[pid]
            for j in range(k):
                site_tok[r, j], tok_mask[r, j] = st.window_tokens(tid, int(st.site_p2[pid][j]))
            if k:
                site_feat[r, :k] = st.site_feat[pid][:k]
                site_mask[r, :k] = True
        mirs = [st.mir_tok[m] for m in self.mids[idx]]
        lm = max(len(m) for m in mirs)
        mir_tok = np.zeros((b, lm, st.mir_dim), dtype=np.float16)
        mir_mask = np.zeros((b, lm), dtype=bool)
        for r, m in enumerate(mirs):
            mir_tok[r, : len(m)] = m
            mir_mask[r, : len(m)] = True
        return {
            "site_tok": site_tok,
            "tok_mask": tok_mask,
            "site_feat": site_feat,
            "site_mask": site_mask,
            "pair_feat": pair_feat,
            "mir_tok": mir_tok,
            "mir_mask": mir_mask,
            "label": self.labels[idx],
        }

    def __call__(self, idx):
        import torch

        return {k: torch.from_numpy(v) for k, v in self.numpy_batch(idx).items()}
