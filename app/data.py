"""Loading and querying the demo bundle.

Kept out of the Streamlit file so it can be tested without a browser: every function here is
pure given a bundle, and the app is a thin layer over it.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TABLES = (
    "scores",
    "lncrna",
    "mirna",
    "known_pairs",
    "tissue_lncrna",
    "tissue_mirna",
    "tissue_map",
)


HF_PREFIX = "hf://datasets/"
# A Path round-trip mangles this differently per platform: POSIX collapses "hf://x" to "hf:/x",
# Windows gives "hf:\\datasets\\x". Separators are normalised before the check and both the
# doubled and single-slash forms are accepted, so the guard behaves the same on either OS.
HF_PREFIXES = (HF_PREFIX, "hf:/datasets/")


def resolve_bundle(location: str | Path) -> Path:
    """A local directory, or an HF dataset repo pulled into the local cache.

    On Spaces the bundle is not in the image -- 12 MB of parquet does not belong in a container
    layer that rebuilds on every code push. It lives in a dataset repo and is fetched once, into
    the cache HF already mounts, so a restart does not re-download it.

        data/demo                      -> used as-is
        hf://datasets/<user>/<repo>    -> downloaded, cached, local path returned
    """
    text = str(location).replace("\\", "/")
    prefix = next((p for p in HF_PREFIXES if text.startswith(p)), None)
    if prefix is None:
        return Path(location)

    from huggingface_hub import hf_hub_download

    repo_id = text[len(prefix) :].strip("/")
    # Tables are required: let a failure raise, with the repo and filename in the message.
    paths = [
        hf_hub_download(repo_id=repo_id, filename=f"{t}.parquet", repo_type="dataset")
        for t in TABLES
    ]
    # The manifest only adds provenance to the Benchmark tab, so a missing one is not fatal.
    with contextlib.suppress(OSError, ValueError):
        hf_hub_download(repo_id=repo_id, filename="manifest.json", repo_type="dataset")
    return Path(paths[0]).parent


@dataclass(frozen=True)
class Bundle:
    scores: pd.DataFrame
    lncrna: pd.DataFrame
    mirna: pd.DataFrame
    known_pairs: pd.DataFrame
    tissue_lncrna: pd.DataFrame
    tissue_mirna: pd.DataFrame
    tissue_map: pd.DataFrame
    manifest: dict

    @classmethod
    def load(cls, location: str | Path) -> Bundle:
        directory = resolve_bundle(location)
        missing = [t for t in TABLES if not (directory / f"{t}.parquet").exists()]
        if missing:
            raise FileNotFoundError(
                f"{directory} is missing {missing}. Run scripts/build_demo_bundle.py."
            )
        frames = {t: pd.read_parquet(directory / f"{t}.parquet") for t in TABLES}
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        return cls(**frames, manifest=manifest)


def label_for_lncrna(row: pd.Series) -> str:
    name = row.get("gene_name")
    return f"{name} ({row.gene_id})" if isinstance(name, str) and name else str(row.gene_id)


def known_set(known: pd.DataFrame) -> set[tuple[str, str]]:
    """Pairs with CLIP evidence, as a set for O(1) lookup.

    The demo must distinguish a prediction from a published fact. Without this, a high score on
    an already-known interaction looks exactly like a discovery.
    """
    return set(zip(known["gene_id"], known["mimat_id"], strict=False))


def top_mirnas(bundle: Bundle, gene_id: str, k: int = 25) -> pd.DataFrame:
    hits = bundle.scores[bundle.scores.gene_id == gene_id].nsmallest(k, "rank_in_lncrna")
    out = hits.merge(bundle.mirna, on="mimat_id", how="left")
    known = known_set(bundle.known_pairs)
    out["known_interaction"] = [(gene_id, m) in known for m in out["mimat_id"]]
    cols = [
        "rank_in_lncrna",
        "mirna_name",
        "mimat_id",
        "probability",
        "n_candidate_sites",
        "known_interaction",
    ]
    return out[[c for c in cols if c in out.columns]].sort_values("rank_in_lncrna")


def top_lncrnas(bundle: Bundle, mimat_id: str, k: int = 25) -> pd.DataFrame:
    hits = bundle.scores[bundle.scores.mimat_id == mimat_id].nsmallest(k, "rank_in_mirna")
    out = hits.merge(bundle.lncrna, on="gene_id", how="left", suffixes=("", "_lnc"))
    known = known_set(bundle.known_pairs)
    out["known_interaction"] = [(g, mimat_id) in known for g in out["gene_id"]]
    cols = [
        "rank_in_mirna",
        "gene_name",
        "gene_id",
        "probability",
        "n_candidate_sites",
        "known_interaction",
    ]
    return out[[c for c in cols if c in out.columns]].sort_values("rank_in_mirna")


def pair_score(bundle: Bundle, gene_id: str, mimat_id: str) -> pd.Series | None:
    hit = bundle.scores[(bundle.scores.gene_id == gene_id) & (bundle.scores.mimat_id == mimat_id)]
    return None if hit.empty else hit.iloc[0]


def tissue_panel(bundle: Bundle, gene_id: str, mimat_id: str) -> pd.DataFrame:
    """Both molecules' expression on one organ axis, each scaled by its own maximum.

    Scaled rather than absolute because the two come from different assays in different units:
    TPM for the lncRNA, atlas intensity for the miRNA. Comparing raw values across them would be
    meaningless. What the panel can honestly show is 'where is each near its own peak, and do
    those places overlap'.
    """
    lnc = bundle.tissue_lncrna[bundle.tissue_lncrna.gene_id == gene_id]
    lnc = lnc.merge(bundle.tissue_map, left_on="tissue", right_on="gtex_tissue", how="inner")
    lnc = lnc[lnc["atlas_organ_system"].notna() & (lnc["atlas_organ_system"] != "")]
    lnc = lnc.groupby("atlas_organ_system", as_index=False)["log1p_tpm"].mean()
    lnc = lnc.rename(columns={"atlas_organ_system": "organ", "log1p_tpm": "lncRNA"})

    mir = bundle.tissue_mirna[bundle.tissue_mirna.mimat_id == mimat_id]
    mir = mir.groupby("organ_system", as_index=False)["log1p_mean_expr"].mean()
    mir = mir.rename(columns={"organ_system": "organ", "log1p_mean_expr": "miRNA"})

    panel = lnc.merge(mir, on="organ", how="outer").fillna(0.0)
    for col in ("lncRNA", "miRNA"):
        peak = panel[col].max()
        panel[col] = panel[col] / peak if peak else 0.0
    panel["both"] = panel[["lncRNA", "miRNA"]].min(axis=1)
    return panel.sort_values("both", ascending=False).reset_index(drop=True)
