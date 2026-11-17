"""The ranking the demo browses by.

Worth testing rather than trusting: a wrong rank here silently reorders every "top 10" the user
sees, and nothing downstream would complain.
"""

from __future__ import annotations

import pandas as pd

from scripts.build_demo_bundle import add_ranks


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "gene_id": ["g1", "g1", "g1", "g2", "g2"],
            "mimat_id": ["m1", "m2", "m3", "m1", "m2"],
            "probability": [0.9, 0.1, 0.5, 0.2, 0.8],
        }
    )


def test_rank_is_per_lncrna_and_starts_at_one() -> None:
    out = add_ranks(frame())
    g1 = out[out.gene_id == "g1"].set_index("mimat_id")["rank_in_lncrna"].to_dict()
    assert g1 == {"m1": 1, "m3": 2, "m2": 3}
    g2 = out[out.gene_id == "g2"].set_index("mimat_id")["rank_in_lncrna"].to_dict()
    assert g2 == {"m2": 1, "m1": 2}


def test_rank_in_mirna_is_the_other_direction() -> None:
    out = add_ranks(frame())
    m1 = out[out.mimat_id == "m1"].set_index("gene_id")["rank_in_mirna"].to_dict()
    assert m1 == {"g1": 1, "g2": 2}


def test_ties_get_distinct_ranks_so_top_k_returns_k_rows() -> None:
    """method="min" would give two rank-1 rows and a top-10 of 11; method="first" cannot."""
    tied = pd.DataFrame({"gene_id": ["g"] * 4, "mimat_id": list("abcd"), "probability": [0.5] * 4})
    out = add_ranks(tied)
    assert sorted(out["rank_in_lncrna"]) == [1, 2, 3, 4]


def test_ranks_are_integers() -> None:
    out = add_ranks(frame())
    assert out["rank_in_lncrna"].dtype.kind == "i"
    assert out["rank_in_mirna"].dtype.kind == "i"
