"""Label each candidate site as experimentally supported, using ENCORI CLIP peak positions.

The pair-level label says only *whether* a lncRNA-miRNA pair interacts. ENCORI also records
*where*, so for positive pairs we can mark which candidate sites overlap a real CLIP peak and
supervise the per-site scorer directly (~16k pair labels -> ~800k site labels).

Adds two columns to data/features/sites/sites.parquet:
  site_label      1 if the candidate lies within a CLIP peak (+/- tolerance), else 0
  label_known     True only for positive pairs whose CLIP peaks mapped to this transcript;
                  elsewhere site_label carries no information and the loss must ignore it.
"""

from __future__ import annotations

import hydra
import numpy as np
import pandas as pd
from omegaconf import DictConfig

from spongescope.features.common import load_table, project_path, write_manifest


def attach_site_labels(
    sites: pd.DataFrame,
    pairs: pd.DataFrame,
    intervals: pd.DataFrame,
    tolerance: int = 10,
) -> pd.DataFrame:
    """sites: candidate sites (pair_id, p2). intervals: CLIP peaks (gene_id, mimat_id, tx_*)."""
    keys = pairs[["pair_id", "gene_id", "mimat_id", "label"]]
    s = sites.merge(keys, on="pair_id", how="left", validate="many_to_one")

    # which pairs have mapped CLIP peaks at all
    truth = intervals[["gene_id", "mimat_id"]].drop_duplicates().assign(label_known=True)
    s = s.merge(truth, on=["gene_id", "mimat_id"], how="left")
    s["label_known"] = s["label_known"].fillna(False) & (s["label"] == 1)

    # a candidate is supported if its p2 falls inside any peak of that pair
    cand = s.loc[s["label_known"], ["pair_id", "p2", "gene_id", "mimat_id"]].reset_index()
    hit = cand.merge(intervals, on=["gene_id", "mimat_id"], how="inner")
    hit = hit[(hit["p2"] >= hit["tx_start"] - tolerance) & (hit["p2"] <= hit["tx_end"] + tolerance)]
    s["site_label"] = 0
    s.loc[s.index.isin(hit["index"].unique()), "site_label"] = 1
    s.loc[~s["label_known"], "site_label"] = 0
    s["site_label"] = s["site_label"].astype(np.int8)
    return s.drop(columns=["gene_id", "mimat_id", "label"])


def report(s: pd.DataFrame, pairs: pd.DataFrame) -> None:
    pos = pairs.loc[pairs.label == 1, "pair_id"]
    per_pair = s.groupby("pair_id").agg(known=("label_known", "max"), hits=("site_label", "sum"))
    known = per_pair[per_pair.known]
    print(f"candidate sites                        {len(s):,}")
    print(f"sites with usable labels               {int(s.label_known.sum()):,}")
    print(f"supported (site_label = 1)             {int(s.site_label.sum()):,}")
    print(f"positive pairs                         {len(pos):,}")
    print(
        f"positive pairs with mapped peaks       {len(known):,}  "
        f"({len(known) / max(len(pos), 1):.1%})"
    )
    print(
        f"  ... of those, >=1 supported site     {(known.hits > 0).sum():,}  "
        f"({(known.hits > 0).mean():.1%})"
    )
    print(f"mean supported sites per labelled pair {known.hits.mean():.2f}")
    frac = s.loc[s.label_known, "site_label"].mean()
    print(
        f"share of labelled candidates supported {frac:.3f}  "
        f"(this is the within-pair signal the aux loss learns)"
    )


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="features")
def main(cfg: DictConfig) -> None:
    import duckdb

    feat = project_path(cfg.paths.features)
    sites_path = feat / "sites" / "sites.parquet"
    sites = pd.read_parquet(sites_path).drop(columns=["site_label", "label_known"], errors="ignore")
    pairs = load_table(cfg.paths.processed, "fct_pairs")

    db = project_path("data") / "spongescope.duckdb"
    con = duckdb.connect(str(db), read_only=True)
    intervals = con.execute(
        "SELECT gene_id, mimat_id, tx_start, tx_end FROM intermediate.int_clip_site_intervals"
    ).fetch_df()
    con.close()

    labelled = attach_site_labels(sites, pairs, intervals, cfg.sites.get("label_tolerance", 10))
    labelled.to_parquet(sites_path, index=False)
    report(labelled, pairs)
    write_manifest(
        feat / "sites" / "LABELS.json",
        {
            "tolerance": cfg.sites.get("label_tolerance", 10),
            "n_sites": len(labelled),
            "n_labelled": int(labelled.label_known.sum()),
            "n_supported": int(labelled.site_label.sum()),
        },
    )


if __name__ == "__main__":
    main()
