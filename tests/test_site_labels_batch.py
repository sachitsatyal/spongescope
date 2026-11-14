"""Site labels must reach the batch, and batching must still work without them (v1 tables)."""

import numpy as np
import pandas as pd

from spongescope.data.site_data import SiteCollate, SiteStore
from spongescope.features.sites import build_site_tables


def _store(tmp_path, with_labels: bool):
    rng = np.random.default_rng(1)
    seqs = ["".join(rng.choice(list("ACGU"), n)) for n in (400, 1500)]
    seqs[1] = seqs[1][:100] + "CUACCUCA" + seqs[1][108:]  # planted let-7a 8mer at p2 = 106
    lnc = pd.DataFrame(
        {
            "transcript_id": ["T0", "T1"],
            "sequence": seqs,
            "transcript_length": [len(s) for s in seqs],
        }
    )
    mir = pd.DataFrame({"mimat_id": ["M0"], "sequence": ["UGAGGUAGUAGGUUGUAUAGUU"]})
    pairs = pd.DataFrame(
        {
            "pair_id": ["G0|M0", "G1|M0"],
            "gene_id": ["G0", "G1"],
            "transcript_id": ["T0", "T1"],
            "mimat_id": ["M0", "M0"],
            "label": [0, 1],
        }
    )
    (tmp_path / "accessibility").mkdir(parents=True, exist_ok=True)
    for t, s in zip(lnc.transcript_id, seqs, strict=True):
        np.save(tmp_path / "accessibility" / f"{t}.npy", rng.random((len(s), 2)).astype(np.float16))
    sites, tab = build_site_tables(pairs, lnc, mir, tmp_path / "accessibility", max_sites=8)
    if with_labels:
        from spongescope.features.site_labels import attach_site_labels

        intervals = pd.DataFrame(
            {"gene_id": ["G1"], "mimat_id": ["M0"], "tx_start": [100], "tx_end": [110]}
        )
        sites = attach_site_labels(sites, pairs, intervals, tolerance=5)
    store = SiteStore(
        lnc,
        mir,
        sites,
        tab,
        tmp_path,
        use_rnafm=False,
        use_accessibility=True,
        window=10,
        max_sites=8,
    )
    return pairs, store, sites


def test_labels_reach_the_batch(tmp_path):
    pairs, store, sites = _store(tmp_path, with_labels=True)
    assert store.has_site_labels
    b = SiteCollate(pairs, store).numpy_batch([0, 1])
    assert b["site_label"].shape == b["site_mask"].shape == b["label_mask"].shape
    # row 0 is the negative pair: no usable site truth
    assert not b["label_mask"][0].any()
    # row 1 is the positive pair with a mapped peak covering the planted 8mer
    assert b["label_mask"][1].any()
    assert b["site_label"][1].sum() == sites[sites.pair_id == "G1|M0"].site_label.sum()
    # a label is only ever set where the site itself exists
    assert not (b["label_mask"] & ~b["site_mask"]).any()
    assert set(np.unique(b["site_label"])) <= {0.0, 1.0}


def test_batching_works_without_labels(tmp_path):
    pairs, store, _ = _store(tmp_path, with_labels=False)
    assert not store.has_site_labels
    b = SiteCollate(pairs, store).numpy_batch([0, 1])
    assert not b["label_mask"].any()
    assert b["site_label"].sum() == 0
