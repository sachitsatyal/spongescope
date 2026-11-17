"""Assemble everything the demo needs into one folder, ready to upload to the Hugging Face Hub.

The demo must not touch DuckDB, Snowflake or the training code: on a free Spaces instance it gets
a few hundred MB of RAM and no warehouse. So every table it reads is written here as a parquet,
and the whole folder is the deployment artifact.

Written to data/demo/:
    scores.parquet        every scored pair + its rank within its lncRNA (the browse index)
    lncrna.parquet        gene/transcript identity, length, tissue breadth
    mirna.parquet         miRNA identity and seed
    known_pairs.parquet   which pairs have CLIP evidence, and their split -- so the demo can mark
                          a prediction as "already known" rather than implying it is novel
    tissue_lncrna.parquet per-tissue lncRNA expression, for the tissue panel
    tissue_mirna.parquet  per-organ miRNA expression, for the tissue panel
    tissue_map.parquet    GTEx tissue -> atlas organ system, so the panel can put both on one axis
    manifest.json         row counts, source versions, and the model's own config

Usage:
    uv run python scripts/build_demo_bundle.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd


def add_ranks(scores: pd.DataFrame) -> pd.DataFrame:
    """Rank each pair within its lncRNA and within its miRNA.

    The demo's two main views are "top miRNAs for this lncRNA" and the reverse. Ranking once
    here keeps the app from sorting hundreds of rows on every interaction, and makes the rank a
    stable number the UI can filter on.

    method="first" rather than "min": ties get distinct ranks in a deterministic order, so
    "top 10" always returns exactly 10 rows.
    """
    out = scores.copy()
    out["rank_in_lncrna"] = (
        out.groupby("gene_id")["probability"].rank(ascending=False, method="first").astype(int)
    )
    out["rank_in_mirna"] = (
        out.groupby("mimat_id")["probability"].rank(ascending=False, method="first").astype(int)
    )
    return out


def read_table(con: duckdb.DuckDBPyConnection, name: str, columns: list[str]) -> pd.DataFrame:
    """Select the columns that actually exist, so a schema change degrades instead of crashing."""
    have = {
        r[0]
        for r in con.execute(
            "select column_name from information_schema.columns "
            "where lower(table_schema) || '.' || lower(table_name) = lower(?)",
            [name],
        ).fetchall()
    }
    keep = [c for c in columns if c in have]
    missing = [c for c in columns if c not in have]
    if missing:
        print(f"  {name}: no column(s) {missing}, continuing without them")
    if not keep:
        sys.exit(f"{name}: none of the requested columns exist ({columns})")
    return con.execute(f"select {', '.join(keep)} from {name}").df()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/spongescope.duckdb"))
    ap.add_argument("--scores", type=Path, default=Path("data/demo/scores"))
    ap.add_argument("--model", type=Path, default=Path("models/spongescope-v1"))
    ap.add_argument("--out", type=Path, default=Path("data/demo"))
    args = ap.parse_args()

    parts = sorted(args.scores.glob("part-*.parquet"))
    if not parts:
        sys.exit(f"no score shards in {args.scores}; run scripts/precompute_scores.py first")
    scores = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    print(f"{len(scores):,} scored pairs from {len(parts)} shard(s)")

    scores = add_ranks(scores)

    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        lncrna = read_table(
            con,
            "marts.dim_lncrna",
            ["gene_id", "gene_name", "transcript_id", "length", "n_sites", "cluster_rep"],
        )
        profile = read_table(
            con,
            "marts.dim_lncrna_tissue_profile",
            ["gene_id", "n_tissues", "n_expressed_tissues", "top_tissue", "max_tpm", "tau"],
        )
        lncrna = lncrna.merge(profile, on="gene_id", how="left")

        mirna = read_table(con, "marts.dim_mirna", ["mimat_id", "mirna_name", "seed", "sequence"])
        known = read_table(
            con,
            "marts.fct_pairs",
            ["gene_id", "mimat_id", "label", "split", "eval_group", "pair_type", "n_cell_contexts"],
        )
        tissue_lnc = read_table(
            con,
            "marts.fct_lncrna_tissue_expression",
            ["gene_id", "tissue", "median_tpm", "log1p_tpm", "is_expressed"],
        )
        tissue_mir = read_table(
            con,
            "marts.fct_mirna_tissue_expression",
            ["mimat_id", "biotype", "organ_system", "tissue", "log1p_mean_expr"],
        )
        # The two sides are measured in different vocabularies -- GTEx tissue names for the
        # lncRNA, atlas organ systems for the miRNA -- so the panel cannot put them on one axis
        # without the mapping. Shipping it means the demo does the join the same way the
        # features did.
        tissue_map = read_table(con, "main.tissue_map", ["gtex_tissue", "atlas_organ_system"])
    finally:
        con.close()

    tissue_mir = tissue_mir[tissue_mir.get("biotype", "tissue") == "tissue"]

    tables = {
        "scores": scores,
        "lncrna": lncrna,
        "mirna": mirna,
        "known_pairs": known[known["label"] == 1] if "label" in known else known,
        "tissue_lncrna": tissue_lnc,
        "tissue_mirna": tissue_mir,
        "tissue_map": tissue_map,
    }
    manifest: dict[str, object] = {
        "built_at": datetime.now(UTC).isoformat(),
        "rows": {},
        "size_mb": {},
    }
    for name, df in tables.items():
        path = args.out / f"{name}.parquet"
        df.to_parquet(path, index=False)
        manifest["rows"][name] = len(df)  # type: ignore[index]
        manifest["size_mb"][name] = round(path.stat().st_size / 1e6, 2)  # type: ignore[index]
        print(f"  {name:16s} {len(df):>9,} rows  {path.stat().st_size / 1e6:6.2f} MB")

    config_path = args.model / "config.json"
    if config_path.exists():
        manifest["model"] = json.loads(config_path.read_text())
    else:
        print(f"  no model config at {config_path}; manifest will not describe the model")

    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    total = sum(manifest["size_mb"].values())  # type: ignore[union-attr]
    print(f"\nbundle: {total:.1f} MB in {args.out}")


if __name__ == "__main__":
    main()
