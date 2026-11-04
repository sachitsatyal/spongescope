"""Unit tests for feature helpers (fast, no GPU or downloads needed)."""

import numpy as np
import pytest

from spongescope.features.common import clean_rna, stitch, window_starts


@pytest.mark.parametrize("n", [1, 200, 999, 1000, 1001, 1500, 2345, 25000])
def test_windows_cover_sequence(n):
    starts = window_starts(n, 1000, 500)
    covered = np.zeros(n, dtype=bool)
    for s in starts:
        assert 0 <= s and s + min(1000, n) <= n
        covered[s : s + 1000] = True
    assert covered.all()


def test_stitch_recovers_positions():
    n, window, stride = 2345, 1000, 500
    truth = np.arange(n, dtype=np.float32)[:, None].repeat(3, axis=1)
    starts = window_starts(n, window, stride)
    chunks = [truth[s : s + window] for s in starts]
    np.testing.assert_allclose(stitch(chunks, starts, n), truth)


def test_clean_rna():
    assert clean_rna("acgtXn") == "ACGUNN"


def test_accessibility_short_sequence():
    pytest.importorskip("RNA")
    from spongescope.features.accessibility import unpaired_profile

    seq = "GGGAAAUCCCAGCUAGCUAGG" * 10
    prof = unpaired_profile(seq, 80, 40, 14)
    assert prof.shape == (len(seq), 2)
    assert np.isfinite(prof).all()
    assert prof.min() >= 0 and prof.max() <= 1
    assert prof[:, 1].mean() <= prof[:, 0].mean() + 1e-6  # 14-nt open is rarer than 1-nt
