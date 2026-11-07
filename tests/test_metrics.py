import numpy as np
import pandas as pd

from spongescope.evaluation.metrics import evaluate, expected_calibration_error, flatten


def _frame(n_genes=60, per_gene=11, signal=1.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_genes):
        split = "val" if g < 20 else "test"
        group = None if split == "val" else ("cold_lncrna" if g < 45 else "cold_both")
        for k in range(per_gene):
            y = int(k == 0)
            s = 1 / (1 + np.exp(-(signal * (2 * y - 1) + rng.normal())))
            rows.append((f"G{g}", f"M{k}", y, split, group, s))
    return pd.DataFrame(
        rows, columns=["gene_id", "mimat_id", "label", "split", "eval_group", "score"]
    )


def test_groups_and_ranges():
    t = evaluate(_frame(), n_boot=200)
    assert set(t.group) == {"val", "test", "test_cold_lncrna", "test_cold_both"}
    for _, r in t.iterrows():
        assert 0.5 < r.auroc <= 1 and r.auroc_lo <= r.auroc <= r.auroc_hi
        assert r.aupr_lo <= r.aupr <= r.aupr_hi
        assert abs(r.pos_rate - 1 / 11) < 1e-9


def test_perfect_and_random():
    df = _frame(signal=50.0)
    assert evaluate(df, n_boot=0).auroc.min() > 0.99
    df["score"] = np.random.default_rng(1).random(len(df))
    assert abs(evaluate(df, n_boot=0).set_index("group").at["test", "auroc"] - 0.5) < 0.12


def test_ece_and_flatten():
    y = np.array([0, 0, 1, 1])
    assert expected_calibration_error(y, np.array([0.0, 0.0, 1.0, 1.0])) == 0
    flat = flatten(evaluate(_frame(), n_boot=0))
    assert "test_cold_both/aupr" in flat


def test_seed_controlled_group():
    df = _frame()
    df["has_seed_site"] = df.index % 2 == 0
    t = evaluate(df, n_boot=0).set_index("group")
    assert "test_seed_controlled" in t.index
    sub = df[(df.split == "test") & df.has_seed_site]
    assert t.at["test_seed_controlled", "n_pos"] + t.at["test_seed_controlled", "n_neg"] == len(sub)
    assert "test_seed_controlled" not in evaluate(_frame(), n_boot=0).group.values


def test_seed_group_excludes_warm_rows():
    df = _frame()
    df["has_seed_site"] = True
    df.loc[df.eval_group == "cold_both", "eval_group"] = "warm"
    t = evaluate(df, n_boot=0).set_index("group")
    n_cold = (df.eval_group == "cold_lncrna").sum()
    assert t.at["test_seed_controlled", "n_pos"] + t.at["test_seed_controlled", "n_neg"] == n_cold
