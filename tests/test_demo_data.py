"""The demo's query layer.

These are the functions that decide what a user is shown, so they are worth testing without a
browser in the loop. The known-interaction flag especially: if it silently returned False, every
published interaction would be presented as a discovery.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data import Bundle, pair_score, tissue_panel, top_lncrnas, top_mirnas


def bundle() -> Bundle:
    scores = pd.DataFrame(
        {
            "gene_id": ["g1", "g1", "g1", "g2"],
            "transcript_id": ["t1", "t1", "t1", "t2"],
            "mimat_id": ["m1", "m2", "m3", "m1"],
            "probability": [0.9, 0.4, 0.1, 0.7],
            "n_candidate_sites": [5, 3, 1, 4],
            "rank_in_lncrna": [1, 2, 3, 1],
            "rank_in_mirna": [1, 1, 1, 2],
        }
    )
    return Bundle(
        scores=scores,
        lncrna=pd.DataFrame({"gene_id": ["g1", "g2"], "gene_name": ["AAA", "BBB"]}),
        mirna=pd.DataFrame({"mimat_id": ["m1", "m2", "m3"], "mirna_name": ["a", "b", "c"]}),
        known_pairs=pd.DataFrame({"gene_id": ["g1"], "mimat_id": ["m2"], "label": [1]}),
        tissue_lncrna=pd.DataFrame(
            {
                "gene_id": ["g1", "g1", "g1"],
                "tissue": ["Brain_Cortex", "Liver", "Lung"],
                "log1p_tpm": [4.0, 2.0, 0.0],
            }
        ),
        tissue_mirna=pd.DataFrame(
            {
                "mimat_id": ["m1", "m1"],
                "organ_system": ["brain", "liver"],
                "log1p_mean_expr": [2.0, 8.0],
            }
        ),
        tissue_map=pd.DataFrame(
            {
                "gtex_tissue": ["Brain_Cortex", "Liver", "Lung"],
                "atlas_organ_system": ["brain", "liver", "lung"],
            }
        ),
        manifest={},
    )


def test_top_mirnas_is_ordered_and_flags_known_interactions() -> None:
    out = top_mirnas(bundle(), "g1")
    assert list(out["mimat_id"]) == ["m1", "m2", "m3"]
    flags = dict(zip(out["mimat_id"], out["known_interaction"], strict=False))
    assert flags == {"m1": False, "m2": True, "m3": False}


def test_top_lncrnas_is_the_other_direction() -> None:
    out = top_lncrnas(bundle(), "m1")
    assert list(out["gene_id"]) == ["g1", "g2"]


def test_top_k_truncates() -> None:
    assert len(top_mirnas(bundle(), "g1", k=2)) == 2


def test_pair_score_returns_none_for_an_unscored_pair() -> None:
    assert pair_score(bundle(), "g2", "m3") is None
    assert pair_score(bundle(), "g1", "m1").probability == 0.9


def test_tissue_panel_scales_each_side_by_its_own_peak() -> None:
    """The two assays are in different units, so only within-molecule fractions are comparable."""
    panel = tissue_panel(bundle(), "g1", "m1")
    assert panel["lncRNA"].max() == 1.0
    assert panel["miRNA"].max() == 1.0
    brain = panel[panel.organ == "brain"].iloc[0]
    assert brain["lncRNA"] == 1.0  # 4.0 is the lncRNA's peak
    assert brain["miRNA"] == 0.25  # 2.0 / 8.0
    assert brain["both"] == 0.25  # min of the two


def test_tissue_panel_ranks_by_overlap_not_by_either_side() -> None:
    """Brain is the lncRNA's best organ and liver the miRNA's; the pair's best is liver.

    brain: lnc 1.0, mir 0.25 -> 0.25.  liver: lnc 0.5, mir 1.0 -> 0.5.
    Ranking by either side alone would put brain first, which is the mistake this guards.
    """
    panel = tissue_panel(bundle(), "g1", "m1")
    assert panel.iloc[0]["organ"] == "liver"
    assert panel.iloc[0]["both"] == 0.5
    assert panel["both"].is_monotonic_decreasing


def test_hf_location_survives_a_path_round_trip(monkeypatch) -> None:
    """Path("hf://x") becomes "hf:/x"; both must still be recognised as a Hub location.

    This is the bug that shipped: the app wrapped the location in Path(), the prefix check
    missed, and the Space looked for a local folder called "hf:".
    """
    import data as mod

    seen: list[str] = []

    def fake_download(repo_id: str, filename: str, **_kwargs: object) -> str:
        seen.append(repo_id)
        return f"/tmp/fake/{filename}"

    import sys
    import types

    stub = types.ModuleType("huggingface_hub")
    stub.hf_hub_download = fake_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", stub)  # type: ignore[attr-defined]

    # The third spelling is whatever this platform's Path does to it: "hf:/datasets/u/r" on
    # POSIX, "hf:\\datasets\\u\\r" on Windows. Asserting the native form means the test fails on
    # the OS where the guard is actually broken.
    spellings = ("hf://datasets/u/r", "hf:/datasets/u/r", str(Path("hf://datasets/u/r")))
    for spelling in spellings:
        seen.clear()
        mod.resolve_bundle(spelling)
        assert seen and set(seen) == {"u/r"}, f"{spelling!r} did not resolve to the repo"


def test_plain_path_is_left_alone() -> None:
    from data import resolve_bundle

    assert resolve_bundle("data/demo") == Path("data/demo")
