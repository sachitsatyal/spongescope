"""Forward/backward checks for the SpongeScope site model on a tiny real batch."""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("lightning")

from spongescope.data.site_data import PAIR_FEAT_DIM, SITE_FEAT_DIM, SiteCollate
from spongescope.models.sitemil import SiteMIL
from tests.test_site_data import make_store


@pytest.mark.parametrize(
    ("rnafm", "acc", "xattn"), [(True, True, True), (False, True, True), (True, False, False)]
)
def test_forward_backward(tmp_path, rnafm, acc, xattn):
    pairs, store = make_store(tmp_path, use_rnafm=rnafm, use_accessibility=acc)
    batch = SiteCollate(pairs, store)([0, 1, 2])
    net = SiteMIL(
        store.tok_dim,
        store.mir_dim,
        SITE_FEAT_DIM,
        PAIR_FEAT_DIM,
        window=10,
        d_model=32,
        n_heads=4,
        n_layers=1,
        ff_dim=64,
        use_cross_attention=xattn,
    )
    logit, attn = net(batch, return_attention=True)
    assert logit.shape == (3,) and torch.isfinite(logit).all()
    has = batch["site_mask"].any(1)
    assert torch.allclose(attn[has].sum(1), torch.ones(int(has.sum())), atol=1e-5)
    assert attn[~has].abs().sum() == 0
    logit.sum().backward()


def test_batch_without_any_sites(tmp_path):
    pairs, store = make_store(tmp_path)
    batch = SiteCollate(pairs, store)([2])  # poly-A miRNA only
    net = SiteMIL(store.tok_dim, store.mir_dim, SITE_FEAT_DIM, PAIR_FEAT_DIM, window=10, d_model=32)
    out = net(batch)
    assert out.shape == (1,) and torch.isfinite(out).all()
