"""Inference-path tests. Skipped until a model has been exported."""

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("safetensors")

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "spongescope-v1"
pytestmark = pytest.mark.skipif(
    not (MODEL / "config.json").exists(), reason="no exported model (run scripts/export_model.py)"
)


@pytest.fixture(scope="module")
def loaded():
    import json

    import pandas as pd

    from spongescope.inference import SpongeScope

    model = SpongeScope.load(MODEL)
    golden = json.loads((MODEL / "golden.json").read_text())
    lnc = pd.read_parquet(ROOT / "data" / "processed" / "dim_lncrna.parquet")
    mir = pd.read_parquet(ROOT / "data" / "processed" / "dim_mirna.parquet")
    row = lnc[lnc.transcript_id == golden["transcript_id"]].iloc[0]
    mrow = mir[mir.mimat_id == golden["mimat_id"]].iloc[0]
    kw = {}
    if model.use_rnafm:
        kw["lncrna_embedding"] = np.load(
            ROOT / "data" / "features" / "rnafm" / "lncrna" / f"{row.transcript_id}.npy"
        ).astype("float32")
        kw["mirna_embedding"] = np.load(ROOT / "data" / "features" / "rnafm" / "mirna.npz")[
            mrow.mimat_id
        ].astype("float32")
    return model, golden, row.sequence, mrow.sequence, kw


def test_golden_output_unchanged(loaded):
    """Fixed input must give the recorded output: catches drift in the inference path."""
    model, golden, lnc, mir, kw = loaded
    p = model.predict(lnc, mir, **kw)
    assert abs(p.probability - golden["probability"]) < 1e-5
    assert p.n_candidate_sites == golden["n_candidate_sites"]


def test_deterministic(loaded):
    model, _, lnc, mir, kw = loaded
    a, b = model.predict(lnc, mir, **kw), model.predict(lnc, mir, **kw)
    assert a.probability == b.probability


def test_output_shape_and_attention(loaded):
    model, _, lnc, mir, kw = loaded
    p = model.predict(lnc, mir, **kw)
    assert 0.0 <= p.probability <= 1.0
    assert len(p.sites) <= model.max_sites
    if p.sites:
        assert abs(sum(s.attention for s in p.sites) - 1.0) < 1e-4
        assert p.sites == sorted(p.sites, key=lambda s: -s.attention)
        assert all(0 <= s.position < len(lnc) for s in p.sites)


def test_pair_with_no_sites(loaded):
    """A miRNA that cannot pair anywhere must still return a probability."""
    model = loaded[0]
    kw = {}
    if model.use_rnafm:
        kw["lncrna_embedding"] = np.zeros((2000, 640), dtype="float32")
        kw["mirna_embedding"] = np.zeros((22, 640), dtype="float32")
    p = model.predict("A" * 2000, "A" * 22, **kw)
    assert p.n_candidate_sites == 0
    assert 0.0 <= p.probability <= 1.0
    assert p.sites == []
