import numpy as np
import pandas as pd

from spongescope.evaluation.compare import paired_bootstrap, seed_summary


def _preds(signal, seed, n_genes=80, per_gene=11):
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_genes):
        for k in range(per_gene):
            y = int(k == 0)
            s = 1 / (1 + np.exp(-(signal * (2 * y - 1) + rng.normal())))
            rows.append((f"G{g}|M{k}", f"G{g}", y, "test", "cold_lncrna", s))
    return pd.DataFrame(
        rows, columns=["pair_id", "gene_id", "label", "split", "eval_group", "score"]
    )


def test_better_model_is_significant():
    res = paired_bootstrap(_preds(2.0, 0), _preds(0.3, 1), "test_cold_lncrna", n_boot=300)
    assert (res.delta > 0).all() and (res.ci_lo > 0).all() and (res.p_one_sided < 0.05).all()


def test_same_model_is_not():
    a = _preds(1.0, 0)
    b = a.assign(score=a.score + np.random.default_rng(5).normal(0, 1e-6, len(a)))
    res = paired_bootstrap(a, b, "test_cold_lncrna", n_boot=300)
    assert (res.ci_lo <= 0).all() and (res.ci_hi >= 0).all()


def test_seed_summary():
    t = pd.DataFrame({"group": ["test"], "auroc": [0.8], "aupr": [0.3], "ece": [0.02]})
    s = seed_summary({"r1": t, "r2": t.assign(auroc=0.9)})
    assert s.n_runs.iloc[0] == 2 and abs(s.auroc_mean.iloc[0] - 0.85) < 1e-9
