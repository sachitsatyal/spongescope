import numpy as np
import pandas as pd

from spongescope.data.paper_style import paper_style_pairs


def test_balanced_random_negatives():
    rng = np.random.default_rng(0)
    rows = [
        (f"G{g}", f"T{g}", f"M{m}", int(rng.random() < 0.1)) for g in range(40) for m in range(30)
    ]
    pairs = pd.DataFrame(rows, columns=["gene_id", "transcript_id", "mimat_id", "label"])
    d = paper_style_pairs(pairs, seed=1)
    pos = set(zip(pairs[pairs.label == 1].gene_id, pairs[pairs.label == 1].mimat_id, strict=True))
    neg = d[d.label == 0]
    assert d.label.sum() == len(neg) == len(pos)
    assert not set(zip(neg.gene_id, neg.mimat_id, strict=True)) & pos
    assert d.pair_id.is_unique
    assert set(d.split) == {"train", "val", "test"}
    assert (d.eval_group == "paper").sum() == (d.split == "test").sum()
