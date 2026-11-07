"""Token data + batching for the LncMiRPath re-implementation.

Each lncRNA is pre-split into 200-nt windows (sequence + dot-bracket tokens). A batch
encodes every distinct lncRNA in it once, and pairs point to their lncRNA by index.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from spongescope.features.common import clean_rna

SEQ_VOCAB = {"A": 1, "C": 2, "G": 3, "U": 4, "N": 5}  # 0 = padding
STR_VOCAB = {".": 1, "(": 2, ")": 3, "[": 4, "]": 5}  # 0 = padding
VOCAB_SIZE = 6


def encode(text: str, vocab: dict[str, int], unknown: int) -> np.ndarray:
    return np.fromiter((vocab.get(c, unknown) for c in text), dtype=np.uint8, count=len(text))


@dataclass
class TokenStore:
    lnc: dict[str, tuple[np.ndarray, np.ndarray]]  # tid -> (seq_win, str_win), each (w, seg)
    mir: dict[str, tuple[np.ndarray, np.ndarray]]  # mimat -> (seq, str), each (len,)


def build_token_store(processed: Path, features: Path) -> TokenStore:
    lnc = pd.read_parquet(processed / "dim_lncrna.parquet")
    mir = pd.read_parquet(processed / "dim_mirna.parquet")
    win = pd.read_parquet(features / "structure" / "lncrna_windows.parquet")
    mstr = dict(pd.read_parquet(features / "structure" / "mirna.parquet").values)

    seqs = {t: clean_rna(s) for t, s in zip(lnc.transcript_id, lnc.sequence, strict=True)}
    lnc_tokens = {}
    for tid, g in win.sort_values(["transcript_id", "window_idx"]).groupby("transcript_id"):
        seq = seqs[tid]
        seq_w = np.stack(
            [
                encode(seq[s : s + len(st)], SEQ_VOCAB, 5)
                for s, st in zip(g.start, g.structure, strict=True)
            ]
        )
        str_w = np.stack([encode(st, STR_VOCAB, 1) for st in g.structure])
        lnc_tokens[tid] = (seq_w, str_w)
    mir_tokens = {
        m: (encode(clean_rna(s), SEQ_VOCAB, 5), encode(mstr[m], STR_VOCAB, 1))
        for m, s in zip(mir.mimat_id, mir.sequence, strict=True)
    }
    return TokenStore(lnc_tokens, mir_tokens)


class PairDataset(Dataset):
    """Items are row positions in `pairs` (a frame with transcript_id, mimat_id, label)."""

    def __init__(self, pairs: pd.DataFrame):
        self.pairs = pairs.reset_index(drop=True)

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, i: int) -> int:
        return i


class Collate:
    def __init__(self, pairs: pd.DataFrame, store: TokenStore):
        self.tids = pairs["transcript_id"].to_numpy()
        self.mids = pairs["mimat_id"].to_numpy()
        self.labels = pairs["label"].to_numpy().astype(np.float32)
        self.store = store

    def __call__(self, idx: list[int]) -> dict[str, torch.Tensor]:
        idx = np.asarray(idx)
        tids = self.tids[idx]
        uniq, lnc_idx = np.unique(tids, return_inverse=True)

        seq_w, str_w, owner, pos = [], [], [], []
        for j, t in enumerate(uniq):
            s, st = self.store.lnc[t]
            seq_w.append(s)
            str_w.append(st)
            owner.append(np.full(len(s), j))
            pos.append(np.arange(len(s)))

        mir = [self.store.mir[m] for m in self.mids[idx]]
        max_m = max(len(m[0]) for m in mir)
        mir_seq = np.zeros((len(mir), max_m), dtype=np.uint8)
        mir_str = np.zeros((len(mir), max_m), dtype=np.uint8)
        for i, (s, st) in enumerate(mir):
            mir_seq[i, : len(s)] = s
            mir_str[i, : len(st)] = st

        return {
            "lnc_seq": torch.from_numpy(np.concatenate(seq_w)).long(),
            "lnc_str": torch.from_numpy(np.concatenate(str_w)).long(),
            "win_owner": torch.from_numpy(np.concatenate(owner)).long(),
            "win_pos": torch.from_numpy(np.concatenate(pos)).long(),
            "n_lnc": torch.tensor(len(uniq)),
            "lnc_idx": torch.from_numpy(lnc_idx).long(),
            "mir_seq": torch.from_numpy(mir_seq).long(),
            "mir_str": torch.from_numpy(mir_str).long(),
            "label": torch.from_numpy(self.labels[idx]),
        }
