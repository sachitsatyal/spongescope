"""LncMiRPath re-implementation (baseline): separate Transformer encoders for sequence and
dot-bracket structure of each RNA, attention pooling, late concatenation, shallow head.

lncRNAs: each 200-nt window is encoded and attention-pooled over tokens, then windows are
attention-pooled into one lncRNA vector (the paper's "attention based pooling of segments").
"""

from __future__ import annotations

import math

import lightning as L
import numpy as np
import torch
from sklearn.metrics import average_precision_score, roc_auc_score
from torch import nn

from spongescope.data.pairs import VOCAB_SIZE


class SinusoidalPE(nn.Module):
    def __init__(self, d: int, max_len: int = 512):
        super().__init__()
        pos = torch.arange(max_len).unsqueeze(1)
        div = torch.exp(torch.arange(0, d, 2) * (-math.log(10000.0) / d))
        pe = torch.zeros(max_len, d)
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe, persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[: x.size(1)].to(x.dtype)


class AttnPool(nn.Module):
    """alpha_i = softmax(w^T tanh(W h_i + b)); z = sum alpha_i h_i (paper eq. 12-13)."""

    def __init__(self, d: int, da: int):
        super().__init__()
        self.proj = nn.Linear(d, da)
        self.score = nn.Linear(da, 1, bias=False)

    def forward(self, h: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        s = self.score(torch.tanh(self.proj(h))).squeeze(-1).float()
        s = s.masked_fill(~mask, float("-inf"))
        a = torch.softmax(s, dim=1).to(h.dtype)
        return torch.einsum("bl,bld->bd", a, h)


class TokenEncoder(nn.Module):
    def __init__(self, d: int, heads: int, layers: int, ff: int, dropout: float, pool_dim: int):
        super().__init__()
        self.emb = nn.Embedding(VOCAB_SIZE, d, padding_idx=0)
        self.pe = SinusoidalPE(d)
        layer = nn.TransformerEncoderLayer(d, heads, ff, dropout, batch_first=True)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.pool = AttnPool(d, pool_dim)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        mask = tokens != 0
        h = self.enc(self.pe(self.emb(tokens)), src_key_padding_mask=~mask)
        return self.pool(h, mask)


class LncMiRPathNet(nn.Module):
    def __init__(
        self,
        d_model=32,
        n_heads=4,
        n_layers=3,
        ff_dim=64,
        dropout=0.1,
        pool_dim=32,
        use_structure=True,
        **_,
    ):
        super().__init__()
        args = (d_model, n_heads, n_layers, ff_dim, dropout, pool_dim)
        self.use_structure = use_structure
        self.lnc_seq, self.mir_seq = TokenEncoder(*args), TokenEncoder(*args)
        self.seg_pool_seq = AttnPool(d_model, pool_dim)
        parts = 2
        if use_structure:
            self.lnc_str, self.mir_str = TokenEncoder(*args), TokenEncoder(*args)
            self.seg_pool_str = AttnPool(d_model, pool_dim)
            parts = 4
        self.head = nn.Sequential(
            nn.Linear(parts * d_model, d_model),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, 1),
        )

    @staticmethod
    def _windows_to_lnc(win: torch.Tensor, owner, pos, n_lnc: int, pool: AttnPool) -> torch.Tensor:
        max_w = int(pos.max()) + 1
        grid = win.new_zeros(n_lnc, max_w, win.size(-1))
        mask = torch.zeros(n_lnc, max_w, dtype=torch.bool, device=win.device)
        grid[owner, pos] = win
        mask[owner, pos] = True
        return pool(grid, mask)

    def forward(self, b: dict[str, torch.Tensor]) -> torch.Tensor:
        n = int(b["n_lnc"])
        lnc = self._windows_to_lnc(
            self.lnc_seq(b["lnc_seq"]), b["win_owner"], b["win_pos"], n, self.seg_pool_seq
        )
        parts = [lnc[b["lnc_idx"]], self.mir_seq(b["mir_seq"])]
        if self.use_structure:
            lnc_s = self._windows_to_lnc(
                self.lnc_str(b["lnc_str"]), b["win_owner"], b["win_pos"], n, self.seg_pool_str
            )
            parts += [lnc_s[b["lnc_idx"]], self.mir_str(b["mir_str"])]
        return self.head(torch.cat(parts, dim=-1)).squeeze(-1)


class LitPairModel(L.LightningModule):
    def __init__(self, model_cfg: dict):
        super().__init__()
        self.save_hyperparameters()
        self.net = LncMiRPathNet(**model_cfg)
        self.lr = model_cfg.get("lr", 1e-3)
        self.wd = model_cfg.get("weight_decay", 0.0)
        self.loss = nn.BCEWithLogitsLoss()
        self._val_p: list[np.ndarray] = []
        self._val_y: list[np.ndarray] = []

    def forward(self, batch):
        return self.net(batch)

    def training_step(self, batch, _):
        loss = self.loss(self(batch), batch["label"])
        self.log("train/loss", loss, prog_bar=True, batch_size=len(batch["label"]))
        return loss

    def validation_step(self, batch, _):
        logits = self(batch)
        self.log("val/loss", self.loss(logits, batch["label"]), batch_size=len(batch["label"]))
        self._val_p.append(torch.sigmoid(logits.float()).cpu().numpy())
        self._val_y.append(batch["label"].cpu().numpy())

    def on_validation_epoch_end(self):
        p, y = np.concatenate(self._val_p), np.concatenate(self._val_y)
        self._val_p.clear()
        self._val_y.clear()
        if 0 < y.sum() < len(y):
            self.log("val/aupr", float(average_precision_score(y, p)), prog_bar=True)
            self.log("val/auroc", float(roc_auc_score(y, p)), prog_bar=True)

    def predict_step(self, batch, _):
        return torch.sigmoid(self(batch).float()).cpu()

    def configure_optimizers(self):
        return torch.optim.AdamW(self.parameters(), lr=self.lr, weight_decay=self.wd)
