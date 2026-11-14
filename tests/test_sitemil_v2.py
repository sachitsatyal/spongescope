"""Per-site head and auxiliary loss (v2). Needs torch, so it runs on the workstation."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("lightning")

from spongescope.data.site_data import PAIR_FEAT_DIM, SITE_FEAT_DIM, SiteCollate
from spongescope.models.sitemil import LitSiteModel, SiteMIL
from tests.test_site_labels_batch import _store

DIMS = {"site_feat_dim": SITE_FEAT_DIM, "pair_feat_dim": PAIR_FEAT_DIM, "window": 10}
SMALL = {"d_model": 32, "n_heads": 4, "n_layers": 1, "ff_dim": 64}


def _batch(tmp_path, with_labels=True):
    pairs, store, _ = _store(tmp_path, with_labels=with_labels)
    return SiteCollate(pairs, store)([0, 1]), store


def test_site_logits_shape_and_grad(tmp_path):
    batch, store = _batch(tmp_path)
    net = SiteMIL(store.tok_dim, store.mir_dim, **DIMS, **SMALL, predict_sites=True)
    logit, site_logits = net(batch, return_site_logits=True)
    assert logit.shape == (2,)
    assert site_logits.shape == batch["site_mask"].shape
    assert torch.isfinite(site_logits).all()
    (logit.sum() + site_logits.sum()).backward()
    assert net.site_head.weight.grad is not None


def test_attention_and_site_logits_together(tmp_path):
    batch, store = _batch(tmp_path)
    net = SiteMIL(store.tok_dim, store.mir_dim, **DIMS, **SMALL, predict_sites=True)
    logit, attn, site_logits = net(batch, return_attention=True, return_site_logits=True)
    assert logit.shape == (2,)
    assert attn.shape == site_logits.shape == batch["site_mask"].shape


def test_site_head_absent_by_default(tmp_path):
    """v1 behaviour is unchanged, and asking for site logits is an explicit error."""
    batch, store = _batch(tmp_path)
    net = SiteMIL(store.tok_dim, store.mir_dim, **DIMS, **SMALL)
    assert net.site_head is None
    assert net(batch).shape == (2,)
    with pytest.raises(ValueError, match="predict_sites"):
        net(batch, return_site_logits=True)


def test_v1_checkpoint_loads_into_v1_shaped_model(tmp_path):
    """Adding the head must not break loading an existing v1 state dict."""
    _, store = _batch(tmp_path)
    v1 = SiteMIL(store.tok_dim, store.mir_dim, **DIMS, **SMALL)
    v2 = SiteMIL(store.tok_dim, store.mir_dim, **DIMS, **SMALL, predict_sites=True)
    v1.load_state_dict(v1.state_dict())  # sanity
    missing, unexpected = v2.load_state_dict(v1.state_dict(), strict=False)
    assert [k for k in missing if not k.startswith("site_head")] == []
    assert unexpected == []


def test_aux_loss_ignores_unlabelled_sites(tmp_path):
    batch, store = _batch(tmp_path)
    cfg = {**SMALL, "predict_sites": True, "site_loss_weight": 0.3}
    lit = LitSiteModel(cfg, {**DIMS, "tok_dim": store.tok_dim, "mir_dim": store.mir_dim})
    _, site_logits = lit(batch, return_site_logits=True)

    term = lit._site_term(site_logits, batch)
    assert torch.isfinite(term) and term > 0

    blank = dict(batch)
    blank["label_mask"] = torch.zeros_like(batch["label_mask"])
    assert float(lit._site_term(site_logits, blank)) == 0.0

    # changing a logit at an unlabelled position must not move the loss
    pos = (~batch["label_mask"] & batch["site_mask"]).nonzero()
    if len(pos):
        bumped = site_logits.clone()
        bumped[tuple(pos[0])] += 10.0
        assert abs(float(lit._site_term(bumped, batch)) - float(term)) < 1e-6


def test_training_step_runs_with_and_without_aux(tmp_path):
    batch, store = _batch(tmp_path)
    dims = {**DIMS, "tok_dim": store.tok_dim, "mir_dim": store.mir_dim}
    for cfg in ({**SMALL, "predict_sites": True, "site_loss_weight": 0.3}, {**SMALL}):
        lit = LitSiteModel(cfg, dims)
        loss = lit.training_step(batch, 0)
        assert torch.isfinite(loss)
        loss.backward()
        assert any(p.grad is not None and torch.isfinite(p.grad).all() for p in lit.parameters())
        assert not np.isnan(float(loss))
