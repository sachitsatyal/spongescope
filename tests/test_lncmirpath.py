"""Shape / NaN checks for the LncMiRPath re-implementation on a tiny fake batch."""

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("lightning")

from spongescope.data.pairs import Collate, TokenStore
from spongescope.models.lncmirpath import LncMiRPathNet


def _store():
    rng = np.random.default_rng(0)
    lnc = {
        "T1": (
            rng.integers(1, 5, (3, 200)).astype(np.uint8),
            rng.integers(1, 4, (3, 200)).astype(np.uint8),
        ),
        "T2": (
            rng.integers(1, 5, (1, 200)).astype(np.uint8),
            rng.integers(1, 4, (1, 200)).astype(np.uint8),
        ),
    }
    mir = {
        "M1": (rng.integers(1, 5, 22).astype(np.uint8), rng.integers(1, 4, 22).astype(np.uint8)),
        "M2": (rng.integers(1, 5, 18).astype(np.uint8), rng.integers(1, 4, 18).astype(np.uint8)),
    }
    return TokenStore(lnc, mir)


def _batch():
    pairs = pd.DataFrame(
        {"transcript_id": ["T1", "T2", "T1"], "mimat_id": ["M1", "M2", "M2"], "label": [1, 0, 0]}
    )
    return Collate(pairs, _store())([0, 1, 2])


def test_collate_shapes():
    b = _batch()
    assert b["lnc_seq"].shape == (4, 200) and int(b["n_lnc"]) == 2
    assert b["mir_seq"].shape == (3, 22) and b["mir_seq"][1, 18:].sum() == 0
    assert b["lnc_idx"].tolist() == [0, 1, 0]


@pytest.mark.parametrize("use_structure", [True, False])
def test_forward(use_structure):
    net = LncMiRPathNet(use_structure=use_structure)
    out = net(_batch())
    assert out.shape == (3,) and torch.isfinite(out).all()
    out.sum().backward()
