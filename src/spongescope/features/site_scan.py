"""Candidate miRNA target-site scanner (pure numpy, used in training and serving).

Coordinates: p2 = 0-based target index that pairs with miRNA nucleotide 2. Without bulges,
miRNA nt k pairs target index p2 - (k - 2); the target nucleotide opposite miRNA nt 1 is p2 + 1.

Site types (strongest first, TargetScan definitions + one non-canonical class):
  8mer          WC pairs at nt 2-8 and an A opposite nt 1
  7mer_m8       WC pairs at nt 2-8
  7mer_a1       WC pairs at nt 2-7 and an A opposite nt 1
  6mer          WC pairs at nt 2-7
  offset_6mer   WC pairs at nt 3-8
  noncanonical  exactly one non-WC position (mismatch or G:U) within nt 2-8
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SITE_TYPES = ("8mer", "7mer_m8", "7mer_a1", "6mer", "offset_6mer", "noncanonical")
N_TYPES = len(SITE_TYPES)

_LUT = np.full(256, 4, dtype=np.int8)
for _ch, _code in zip("ACGU", range(4), strict=True):
    _LUT[ord(_ch)] = _code
    _LUT[ord(_ch.lower())] = _code
_LUT[ord("T")] = _LUT[ord("t")] = 3
_COMP = np.array([3, 2, 1, 0, 5], dtype=np.int8)  # A-U, C-G; N (4) never pairs


def encode(seq: str) -> np.ndarray:
    """RNA/DNA string -> int8 codes A=0 C=1 G=2 U/T=3, anything else 4."""
    return _LUT[np.frombuffer(seq.encode("ascii", "replace"), dtype=np.uint8)]


@dataclass
class Sites:
    p2: np.ndarray  # (n,) int64
    type_id: np.ndarray  # (n,) int8, index into SITE_TYPES
    wc: np.ndarray  # (n, 7) bool, WC pair at miRNA nt 2..8
    n_wobble: np.ndarray  # (n,) int8, G:U pairs within nt 2..8
    a1: np.ndarray  # (n,) bool, target A opposite miRNA nt 1
    supp: np.ndarray  # (n,) int8, best 3' supplementary WC pairs at nt 13-16 (0-4)

    def __len__(self) -> int:
        return len(self.p2)


def _empty() -> Sites:
    return Sites(
        p2=np.zeros(0, np.int64),
        type_id=np.zeros(0, np.int8),
        wc=np.zeros((0, 7), bool),
        n_wobble=np.zeros(0, np.int8),
        a1=np.zeros(0, bool),
        supp=np.zeros(0, np.int8),
    )


def scan(target: np.ndarray, mirna: np.ndarray) -> Sites:
    """All candidate sites of `mirna` in `target` (both int8 codes from `encode`)."""
    n = len(target)
    if n < 7 or len(mirna) < 8:
        return _empty()
    idx = np.arange(6, n)
    wc = np.empty((len(idx), 7), dtype=bool)
    wob = np.empty((len(idx), 7), dtype=bool)
    for j, k in enumerate(range(2, 9)):
        t = target[idx - (k - 2)]
        m = mirna[k - 1]
        wc[:, j] = t == _COMP[m]
        wob[:, j] = ((m == 3) & (t == 2)) | ((m == 2) & (t == 3))
    a1 = (idx + 1 < n) & (target[np.minimum(idx + 1, n - 1)] == 0)
    wc2_7, wc8, wc3_8 = wc[:, :6].all(1), wc[:, 6], wc[:, 1:].all(1)

    type_id = np.full(len(idx), -1, dtype=np.int8)
    type_id[(7 - wc.sum(1)) == 1] = 5  # weakest first; stronger classes overwrite
    type_id[wc3_8 & ~wc[:, 0]] = 4
    type_id[wc2_7 & ~wc8 & ~a1] = 3
    type_id[wc2_7 & ~wc8 & a1] = 2
    type_id[wc2_7 & wc8 & ~a1] = 1
    type_id[wc2_7 & wc8 & a1] = 0
    keep = type_id >= 0
    p2 = idx[keep]

    supp = np.zeros(len(p2), dtype=np.int8)
    if len(mirna) >= 16 and len(p2):
        for off in range(-2, 3):  # allow small loops/bulges between seed and 3' region
            cnt = np.zeros(len(p2), dtype=np.int8)
            for k in range(13, 17):
                q = p2 - (k - 2) + off
                ok = (q >= 0) & (q < n)
                cnt += (ok & (target[np.clip(q, 0, n - 1)] == _COMP[mirna[k - 1]])).astype(np.int8)
            supp = np.maximum(supp, cnt)

    return Sites(
        p2=p2.astype(np.int64),
        type_id=type_id[keep],
        wc=wc[keep],
        n_wobble=wob[keep].sum(1).astype(np.int8),
        a1=a1[keep],
        supp=supp,
    )
