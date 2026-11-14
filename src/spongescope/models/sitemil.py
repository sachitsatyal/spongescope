"""SpongeScope site model: per-site encoder with miRNA cross-attention + attention-MIL.

  site window tokens (RNA-FM + accessibility) --TransformerDecoder(cross-attends miRNA)--> pool
  + site features (type, pairing, 3' supplementary, AU, accessibility)       -> site embedding
  attention-MIL over a pair's sites (+ learned "no site" vector)             -> pair embedding
  pair embedding + pair features (site counts, length)                        -> logit
The MIL attention weights say which site drove each prediction (binding-site track in the demo).

With predict_sites=True the model also emits a logit per site, trained against ENCORI CLIP
positions (v2). The head is only created when asked, so v1 checkpoints still load.
"""

from __future__ import annotations

import lightning as L
import numpy as np
import torch
from sklearn.metrics import average_precision_score, roc_auc_score
from torch import nn


class AttnPool(nn.Module):
    def __init__(self, d: int):
        super().__init__()
        self.proj = nn.Linear(d, d)
        self.score = nn.Linear(d, 1, bias=False)

    def forward(self, h: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        s = self.score(torch.tanh(self.proj(h))).squeeze(-1).float()
        s = s.masked_fill(~mask, float("-inf"))
        a = torch.softmax(s, dim=-1)
        return torch.einsum("...l,...ld->...d", a.to(h.dtype), h), a


class SiteMIL(nn.Module):
    def __init__(
        self,
        tok_dim: int,
        mir_dim: int,
        site_feat_dim: int,
        pair_feat_dim: int,
        window: int = 40,
        d_model: int = 128,
        n_heads: int = 4,
        n_layers: int = 2,
        ff_dim: int = 256,
        dropout: float = 0.1,
        use_cross_attention: bool = True,
        max_mir_len: int = 40,
        predict_sites: bool = False,
        **_,
    ):
        super().__init__()
        d = d_model
        self.cross = use_cross_attention
        self.tok_proj = nn.Sequential(nn.Linear(tok_dim, d), nn.LayerNorm(d))
        self.tok_pos = nn.Parameter(torch.zeros(2 * window + 1, d))
        self.mir_proj = nn.Sequential(nn.Linear(mir_dim, d), nn.LayerNorm(d))
        self.mir_pos = nn.Parameter(torch.zeros(max_mir_len, d))
        nn.init.normal_(self.tok_pos, std=0.02)
        nn.init.normal_(self.mir_pos, std=0.02)
        if self.cross:
            layer = nn.TransformerDecoderLayer(d, n_heads, ff_dim, dropout, batch_first=True)
            self.blocks = nn.TransformerDecoder(layer, n_layers)
        else:  # ablation: encode the site alone, give the model a pooled miRNA vector
            layer = nn.TransformerEncoderLayer(d, n_heads, ff_dim, dropout, batch_first=True)
            self.blocks = nn.TransformerEncoder(layer, n_layers, enable_nested_tensor=False)
            self.mir_pool = AttnPool(d)
        self.tok_pool = AttnPool(d)
        self.feat_mlp = nn.Sequential(nn.Linear(site_feat_dim, d), nn.ReLU(), nn.Linear(d, d))
        in_dim = 2 * d if self.cross else 3 * d
        self.site_mlp = nn.Sequential(
            nn.Linear(in_dim, d), nn.ReLU(), nn.Dropout(dropout), nn.Linear(d, d)
        )
        self.mil_pool = AttnPool(d)
        self.site_head = nn.Linear(d, 1) if predict_sites else None
        self.no_site = nn.Parameter(torch.zeros(d))
        self.head = nn.Sequential(
            nn.Linear(d + pair_feat_dim, d), nn.ReLU(), nn.Dropout(dropout), nn.Linear(d, 1)
        )

    def forward(
        self,
        b: dict[str, torch.Tensor],
        return_attention: bool = False,
        return_site_logits: bool = False,
    ):
        site_mask = b["site_mask"]
        bsz, n_site = site_mask.shape
        sb, ss = site_mask.nonzero(as_tuple=True)
        mir = self.mir_proj(b["mir_tok"].float()) + self.mir_pos[: b["mir_tok"].shape[1]]
        e_all = None
        if len(sb):
            tok = b["site_tok"][sb, ss].float()
            tmask = b["tok_mask"][sb, ss]
            h = self.tok_proj(tok) + self.tok_pos
            mem, mmask = mir[sb], b["mir_mask"][sb]
            if self.cross:
                h = self.blocks(h, mem, tgt_key_padding_mask=~tmask, memory_key_padding_mask=~mmask)
                parts = [self.tok_pool(h, tmask)[0]]
            else:
                h = self.blocks(h, src_key_padding_mask=~tmask)
                parts = [self.tok_pool(h, tmask)[0], self.mir_pool(mem, mmask)[0]]
            parts.append(self.feat_mlp(b["site_feat"][sb, ss]))
            e = self.site_mlp(torch.cat([p.float() for p in parts], dim=-1))
            e_all = e.new_zeros(bsz, n_site, e.shape[-1])
            e_all[sb, ss] = e
        if e_all is None:
            e_all = mir.new_zeros(bsz, n_site, self.no_site.shape[0])
        has = site_mask.any(1)
        safe = site_mask.clone()
        safe[~has, 0] = True
        z, attn = self.mil_pool(e_all, safe)
        z = torch.where(has[:, None], z.float(), self.no_site.float().expand(bsz, -1))
        logit = self.head(torch.cat([z, b["pair_feat"].float()], dim=-1)).squeeze(-1)
        out = [logit]
        if return_attention:
            out.append(attn * site_mask)
        if return_site_logits:
            if self.site_head is None:
                raise ValueError("model was built with predict_sites=False")
            out.append(self.site_head(e_all).squeeze(-1))
        return out[0] if len(out) == 1 else tuple(out)


class LitSiteModel(L.LightningModule):
    def __init__(self, model_cfg: dict, dims: dict):
        super().__init__()
        self.save_hyperparameters()
        self.net = SiteMIL(**dims, **model_cfg)
        self.lr = model_cfg.get("lr", 3e-4)
        self.wd = model_cfg.get("weight_decay", 0.01)
        self.site_loss_weight = float(model_cfg.get("site_loss_weight", 0.0))
        self.predicts_sites = bool(model_cfg.get("predict_sites", False))
        self.loss = nn.BCEWithLogitsLoss()
        self.site_loss = nn.BCEWithLogitsLoss(reduction="none")
        self._p: list[np.ndarray] = []
        self._y: list[np.ndarray] = []

    def forward(self, batch, **kw):
        return self.net(batch, **kw)

    def _site_term(self, site_logits, batch) -> torch.Tensor:
        """BCE over candidate sites, averaged only where a CLIP peak mapped (label_mask)."""
        mask = batch["label_mask"] & batch["site_mask"]
        if not mask.any():
            return site_logits.sum() * 0.0
        per = self.site_loss(site_logits.float(), batch["site_label"].float())
        return (per * mask).sum() / mask.sum()

    def training_step(self, batch, _):
        n = len(batch["label"])
        if self.site_loss_weight > 0 and self.predicts_sites:
            logit, site_logits = self(batch, return_site_logits=True)
            pair_loss = self.loss(logit, batch["label"])
            site_term = self._site_term(site_logits, batch)
            loss = pair_loss + self.site_loss_weight * site_term
            self.log("train/pair_loss", pair_loss, batch_size=n)
            self.log("train/site_loss", site_term, prog_bar=True, batch_size=n)
        else:
            loss = self.loss(self(batch), batch["label"])
        self.log("train/loss", loss, prog_bar=True, batch_size=n)
        return loss

    def validation_step(self, batch, _):
        logits = self(batch)
        self.log("val/loss", self.loss(logits, batch["label"]), batch_size=len(batch["label"]))
        self._p.append(torch.sigmoid(logits.float()).cpu().numpy())
        self._y.append(batch["label"].cpu().numpy())

    def on_validation_epoch_end(self):
        p, y = np.concatenate(self._p), np.concatenate(self._y)
        self._p.clear()
        self._y.clear()
        if 0 < y.sum() < len(y):
            self.log("val/aupr", float(average_precision_score(y, p)), prog_bar=True)
            self.log("val/auroc", float(roc_auc_score(y, p)), prog_bar=True)

    def predict_step(self, batch, _):
        return self(batch).float().cpu()  # logits; temperature scaling happens afterwards

    def configure_optimizers(self):
        return torch.optim.AdamW(self.parameters(), lr=self.lr, weight_decay=self.wd)
