import numpy as np
import pandas as pd

from spongescope.features.site_labels import attach_site_labels


def _fixture():
    sites = pd.DataFrame(
        {
            "pair_id": ["G1|M1"] * 3 + ["G2|M1"] * 2 + ["G3|M1"] * 2,
            "p2": [100, 500, 900, 100, 500, 100, 500],
        }
    )
    pairs = pd.DataFrame(
        {
            "pair_id": ["G1|M1", "G2|M1", "G3|M1"],
            "gene_id": ["G1", "G2", "G3"],
            "mimat_id": ["M1", "M1", "M1"],
            "label": [1, 1, 0],  # G1 positive w/ peaks, G2 positive w/o peaks, G3 negative
        }
    )
    intervals = pd.DataFrame(
        {
            "gene_id": ["G1", "G1"],
            "mimat_id": ["M1", "M1"],
            "tx_start": [495, 880],
            "tx_end": [515, 890],
        }
    )
    return sites, pairs, intervals


def test_supported_sites_marked_only_for_mapped_positives():
    sites, pairs, intervals = _fixture()
    out = attach_site_labels(sites, pairs, intervals, tolerance=10)
    g1 = out[out.pair_id == "G1|M1"].set_index("p2")
    assert g1.at[500, "site_label"] == 1  # inside peak 495-515
    assert g1.at[900, "site_label"] == 1  # within tolerance of peak 880-890
    assert g1.at[100, "site_label"] == 0  # no peak nearby
    assert g1["label_known"].all()
    # positive pair with no mapped peaks, and the negative pair: unusable, never supported
    for pid in ("G2|M1", "G3|M1"):
        sub = out[out.pair_id == pid]
        assert not sub["label_known"].any()
        assert (sub["site_label"] == 0).all()


def test_tolerance_is_respected():
    sites, pairs, intervals = _fixture()
    strict = attach_site_labels(sites, pairs, intervals, tolerance=0)
    g1 = strict[strict.pair_id == "G1|M1"].set_index("p2")
    assert g1.at[500, "site_label"] == 1
    assert g1.at[900, "site_label"] == 0  # 10 nt past the peak, now excluded


def test_shape_dtypes_and_columns_preserved():
    sites, pairs, intervals = _fixture()
    out = attach_site_labels(sites, pairs, intervals)
    assert len(out) == len(sites)
    assert list(out.pair_id) == list(sites.pair_id) and list(out.p2) == list(sites.p2)
    assert out.site_label.dtype == np.int8
    assert out.label_known.dtype == bool
    assert not {"gene_id", "mimat_id", "label"} & set(out.columns)


def test_rerunnable_and_no_sites_case():
    sites, pairs, intervals = _fixture()
    once = attach_site_labels(sites, pairs, intervals)
    twice = attach_site_labels(once.drop(columns=["site_label", "label_known"]), pairs, intervals)
    pd.testing.assert_frame_equal(once, twice)
    empty = attach_site_labels(sites, pairs, intervals.iloc[:0])
    assert not empty.label_known.any() and (empty.site_label == 0).all()
