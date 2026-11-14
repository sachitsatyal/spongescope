"""Single inference path for SpongeScope, shared by training eval, the API and the demo.

Loads an exported model (safetensors + config.json) and scores one lncRNA-miRNA pair,
returning a calibrated probability plus per-site scores. Site features are built with the
same functions used in training (`features.sites.site_rows`, `data.site_data.site_matrix`),
so serving cannot drift from training.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from spongescope.data.site_data import SITE_FEAT_DIM, one_hot, pair_matrix, site_matrix
from spongescope.features.common import clean_rna
from spongescope.features.site_scan import SITE_TYPES, encode
from spongescope.features.sites import COUNT_COLS, INT_SITE_COLS, SITE_COLS, site_rows


@dataclass
class Site:
    position: int  # 0-based index on the lncRNA paired with miRNA nt 2
    site_type: str
    attention: float  # share of the pair's prediction this site accounts for
    accessibility: float


@dataclass
class Prediction:
    probability: float
    logit: float
    n_candidate_sites: int
    sites: list[Site] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "probability": self.probability,
            "logit": self.logit,
            "n_candidate_sites": self.n_candidate_sites,
            "sites": [vars(s) for s in self.sites],
        }


def _site_frame(feats: np.ndarray) -> pd.DataFrame:
    """Same column names and dtypes as the training site table (features.sites)."""
    df = pd.DataFrame(feats, columns=SITE_COLS[1:])
    df[INT_SITE_COLS] = df[INT_SITE_COLS].astype(np.int64)
    return df


def accessibility_profile(seq: str, cfg: dict) -> np.ndarray:
    """P(unpaired) per nucleotide via ViennaRNA; costs ~15 ms for a 1.5 kb transcript."""
    from spongescope.features.accessibility import unpaired_profile

    a = cfg["accessibility"]
    return unpaired_profile(seq, a["window_size"], a["max_bp_span"], a["ulength"])


class SpongeScope:
    """Loaded, calibrated model. Build once, call predict() many times."""

    def __init__(self, net, config: dict):
        self.net = net
        self.config = config
        self.window = config["window"]
        self.max_sites = config["max_sites"]
        self.au_window = config["au_window"]
        self.use_rnafm = config["model"]["use_rnafm"]
        self.use_accessibility = config["model"]["use_accessibility"]
        self.temperature = config["temperature"]

    @classmethod
    def load(cls, path: str | Path, device: str = "cpu") -> SpongeScope:
        from safetensors.torch import load_file

        from spongescope.models.sitemil import SiteMIL

        path = Path(path)
        config = json.loads((path / "config.json").read_text())
        net = SiteMIL(**config["dims"], **config["model"])
        net.load_state_dict(load_file(path / "model.safetensors"))
        net.eval().to(device)
        for p in net.parameters():
            p.requires_grad_(False)
        return cls(net, config)

    def _tokens(self, emb: np.ndarray, acc: np.ndarray | None, p2: int, n: int) -> tuple:
        w, lo, hi = self.window, p2 - self.window, p2 + self.window + 1
        a, b = max(lo, 0), min(hi, n)
        dim = 640 if self.use_rnafm else 4
        tok = np.zeros((2 * w + 1, dim + (2 if self.use_accessibility else 0)), dtype=np.float32)
        mask = np.zeros(2 * w + 1, dtype=bool)
        tok[a - lo : b - lo, :dim] = emb[a:b]
        if self.use_accessibility and acc is not None:
            tok[a - lo : b - lo, dim:] = acc[a:b]
        mask[a - lo : b - lo] = True
        return tok, mask

    def predict(
        self,
        lncrna_seq: str,
        mirna_seq: str,
        lncrna_embedding: np.ndarray | None = None,
        mirna_embedding: np.ndarray | None = None,
        accessibility: np.ndarray | None = None,
    ) -> Prediction:
        """Score one pair. Pass cached arrays where available; anything missing is computed."""
        import torch

        lnc = clean_rna(lncrna_seq)
        mir = clean_rna(mirna_seq)
        target, mir_codes = encode(lnc), encode(mir)
        n = len(lnc)

        if accessibility is None:
            accessibility = accessibility_profile(lnc, self.config)
        au_cum = np.concatenate([[0], np.cumsum((target == 0) | (target == 3))])
        feats, counts = site_rows(
            target, mir_codes, accessibility, au_cum, self.max_sites, self.au_window
        )

        if self.use_rnafm:
            if lncrna_embedding is None or mirna_embedding is None:
                raise ValueError(
                    "this model uses RNA-FM: pass lncrna_embedding and mirna_embedding "
                    "(cached .npy / mirna.npz, or computed with features.rnafm_embed)"
                )
            lnc_emb, mir_emb = np.asarray(lncrna_embedding), np.asarray(mirna_embedding)
        else:
            lnc_emb, mir_emb = one_hot(target), one_hot(mir_codes)

        k = max(len(feats), 1)
        tok = np.zeros(
            (1, k, 2 * self.window + 1, lnc_emb.shape[1] + (2 if self.use_accessibility else 0)),
            dtype=np.float32,
        )
        tok_mask = np.zeros((1, k, 2 * self.window + 1), dtype=bool)
        site_feat = np.zeros((1, k, SITE_FEAT_DIM), dtype=np.float32)
        site_mask = np.zeros((1, k), dtype=bool)
        sdf = _site_frame(feats)
        if len(feats):
            site_feat[0, : len(feats)] = site_matrix(sdf, self.use_accessibility)
            site_mask[0, : len(feats)] = True
            for j, p2 in enumerate(sdf["p2"]):
                tok[0, j], tok_mask[0, j] = self._tokens(lnc_emb, accessibility, int(p2), n)

        ptab = pd.DataFrame(
            [[int(counts.sum()), len(feats), *counts.tolist(), float(np.log10(max(n, 1)))]],
            columns=["n_sites", "n_kept", *COUNT_COLS, "log_len"],
        )
        batch = {
            "site_tok": torch.from_numpy(tok),
            "tok_mask": torch.from_numpy(tok_mask),
            "site_feat": torch.from_numpy(site_feat),
            "site_mask": torch.from_numpy(site_mask),
            "pair_feat": torch.from_numpy(pair_matrix(ptab)),
            "mir_tok": torch.from_numpy(mir_emb.astype(np.float32)[None]),
            "mir_mask": torch.ones((1, len(mir_emb)), dtype=torch.bool),
        }
        with torch.no_grad():
            logit, attn = self.net(batch, return_attention=True)
        logit = float(logit[0])
        prob = 1.0 / (1.0 + np.exp(-logit / self.temperature))

        sites = []
        if len(feats):
            a = attn[0].numpy()
            sites = [
                Site(
                    position=int(sdf["p2"].iloc[j]),
                    site_type=SITE_TYPES[int(sdf["type_id"].iloc[j])],
                    attention=float(a[j]),
                    accessibility=float(sdf["acc_site"].iloc[j]),
                )
                for j in range(len(feats))
            ]
            sites.sort(key=lambda s: -s.attention)
        return Prediction(prob, logit, int(counts.sum()), sites)
