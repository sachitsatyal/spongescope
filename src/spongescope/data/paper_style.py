"""Paper-style dataset (positive control), reproducing the original LncMiRPath setup:
negatives = random pairing of RNAs that are not known to interact, balanced 1:1, and a
random 80/10/10 split of *pairs* (the same lncRNAs and miRNAs appear in train and test).

Random pairing leaves a node-degree shortcut: lncRNAs/miRNAs with many positives are rarely
drawn as negatives in proportion, so "is this a busy lncRNA / miRNA?" predicts the label.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def paper_style_pairs(pairs: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pos = pairs[pairs.label == 1].drop_duplicates(["gene_id", "mimat_id"])
    pos = pos.assign(pair_type="clip_positive")
    genes = pairs[["gene_id", "transcript_id"]].drop_duplicates("gene_id").reset_index(drop=True)
    mirs = np.array(sorted(pairs.mimat_id.unique()))
    known = set(zip(pos.gene_id, pos.mimat_id, strict=True))

    neg_g, neg_m, seen = [], [], set()
    while len(neg_g) < len(pos):
        gi = rng.integers(0, len(genes), 4 * len(pos))
        mi = rng.integers(0, len(mirs), 4 * len(pos))
        for g, m in zip(genes.gene_id.to_numpy()[gi], mirs[mi], strict=True):
            if (g, m) not in known and (g, m) not in seen:
                seen.add((g, m))
                neg_g.append(g)
                neg_m.append(m)
                if len(neg_g) == len(pos):
                    break
    neg = pd.DataFrame({"gene_id": neg_g, "mimat_id": neg_m}).merge(genes, on="gene_id")
    neg["label"], neg["pair_type"] = 0, "random_pair"

    keep = ["gene_id", "transcript_id", "mimat_id", "label", "pair_type"]
    d = pd.concat([pos[keep], neg[keep]], ignore_index=True)
    d = d.iloc[rng.permutation(len(d))].reset_index(drop=True)  # Fisher-Yates shuffle
    u = rng.random(len(d))
    d["split"] = np.where(u < 0.8, "train", np.where(u < 0.9, "val", "test"))
    d["eval_group"] = np.where(d["split"] == "test", "paper", None)
    d["pair_id"] = d.gene_id + "|" + d.mimat_id
    d["has_seed_site"] = False
    return d
