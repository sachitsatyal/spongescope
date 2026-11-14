import numpy as np
import pandas as pd

from spongescope.baselines.site_gbm import FEATURES, pair_features
from spongescope.features.sites import COUNT_COLS, build_site_tables


def _toy(n_lnc=6, n_mir=5, seed=0):
    rng = np.random.default_rng(seed)
    b = np.array(list("ACGU"))
    lnc = pd.DataFrame(
        {
            "transcript_id": [f"T{i}" for i in range(n_lnc)],
            "sequence": ["".join(rng.choice(b, rng.integers(300, 3000))) for _ in range(n_lnc)],
        }
    )
    lnc["transcript_length"] = lnc.sequence.str.len()
    mir = pd.DataFrame(
        {
            "mimat_id": [f"M{j}" for j in range(n_mir)],
            "sequence": ["".join(rng.choice(b, 22)) for _ in range(n_mir)],
        }
    )
    pairs = pd.DataFrame(
        [
            (f"G{i}|M{j}", f"G{i}", f"T{i}", f"M{j}", int(rng.random() < 0.2))
            for i in range(n_lnc)
            for j in range(n_mir)
        ],
        columns=["pair_id", "gene_id", "transcript_id", "mimat_id", "label"],
    )
    return pairs, lnc, mir


def test_tables_consistent_and_capped():
    pairs, lnc, mir = _toy()
    sites, tab = build_site_tables(pairs, lnc, mir, None, max_sites=3)
    assert len(tab) == len(pairs) and tab.pair_id.is_unique
    assert (tab.n_kept == np.minimum(tab.n_sites, 3)).all()
    assert (tab[COUNT_COLS].sum(1) == tab.n_sites).all()
    assert (
        sites.groupby("pair_id").size().reindex(tab.pair_id, fill_value=0).tolist()
        == tab.n_kept.tolist()
    )
    assert sites.groupby("pair_id")["p2"].apply(lambda s: s.is_monotonic_increasing).all()
    assert sites.au_local.between(0, 1).all()


def test_site_gbm_features():
    pairs, lnc, mir = _toy()
    sites, tab = build_site_tables(pairs, lnc, mir, None, max_sites=3)
    f = pair_features(tab, sites)
    assert set(FEATURES) <= set(f.columns) and not f[FEATURES].isna().any().any()
