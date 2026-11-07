"""Canonical miRNA seed-site matching (TargetScan site definitions).

A target site is written 5'->3' on the lncRNA. For miRNA nucleotides 2-8 (the seed):
  8mer    = revcomp(nt 2-8) + "A"
  7mer-m8 = revcomp(nt 2-8)
  7mer-A1 = revcomp(nt 2-7) + "A"
  6mer    = revcomp(nt 2-7)
Counts include overlaps; larger site types are also counted by the smaller ones.
"""

from __future__ import annotations

import re

import numpy as np

_COMP = str.maketrans("ACGUN", "UGCAN")


def revcomp(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def site_patterns(mirna: str) -> dict[str, str]:
    m = mirna.upper().replace("T", "U")
    s7, s6 = m[1:8], m[1:7]
    return {
        "8mer": revcomp(s7) + "A",
        "7mer_m8": revcomp(s7),
        "7mer_a1": revcomp(s6) + "A",
        "6mer": revcomp(s6),
    }


def find_sites(target: str, pattern: str) -> np.ndarray:
    """0-based start positions of all (overlapping) occurrences."""
    return np.array([m.start() for m in re.finditer(f"(?={pattern})", target)], dtype=np.int64)


def pair_features(target: str, mirna: str, acc: np.ndarray | None = None) -> dict[str, float]:
    """Seed-site counts + accessibility of the best 7mer-m8 site for one lncRNA-miRNA pair.

    acc: (len(target), 2) array from features/accessibility (col 0 = P(unpaired) per nt).
    """
    pats = site_patterns(mirna)
    starts = {k: find_sites(target, v) for k, v in pats.items()}
    n_kb = max(len(target), 1) / 1000
    out = {f"n_{k}": float(len(v)) for k, v in starts.items()}
    out["dens_7mer_m8"] = out["n_7mer_m8"] / n_kb
    out["dens_6mer"] = out["n_6mer"] / n_kb
    best = 0.0
    if acc is not None and len(starts["7mer_m8"]):
        p1 = acc[:, 0].astype(np.float32)
        best = max(float(p1[s : s + 7].mean()) for s in starts["7mer_m8"])
    out["best_site_acc"] = best
    return out
