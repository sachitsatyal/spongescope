import numpy as np

from spongescope.features.seed_sites import find_sites, pair_features, revcomp, site_patterns

LET7A = "UGAGGUAGUAGGUUGUAUAGUU"  # hsa-let-7a-5p


def test_let7_site_patterns():
    p = site_patterns(LET7A)
    assert p["7mer_m8"] == "CUACCUC"  # classic let-7 seed site
    assert p["8mer"] == "CUACCUCA"
    assert p["6mer"] == "UACCUC"
    assert revcomp("ACGU") == "ACGU"


def test_counts_and_accessibility():
    target = "GG" + "CUACCUCA" + "AAAA" + "CUACCUC" + "GG"
    assert list(find_sites(target, "CUACCUC")) == [2, 14]
    acc = np.zeros((len(target), 2), dtype=np.float32)
    acc[14:21, 0] = 0.9
    f = pair_features(target, LET7A, acc)
    assert f["n_8mer"] == 1 and f["n_7mer_m8"] == 2
    assert abs(f["best_site_acc"] - 0.9) < 1e-6
