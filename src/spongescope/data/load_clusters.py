"""Load the MMseqs2 cluster TSV (from Colab) into DuckDB as raw.lnc_clusters."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
TSV = ROOT / "data" / "interim" / "clustering" / "lnc_cluster.tsv"
DB = ROOT / "data" / "spongescope.duckdb"


def main() -> None:
    if not TSV.exists():
        raise FileNotFoundError(f"{TSV} not found. Run the Colab step first.")
    df = pd.read_csv(TSV, sep="\t", header=None, names=["cluster_rep", "gene_id"], dtype=str)
    con = duckdb.connect(str(DB))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw").fetchall()
    con.register("df_view", df)
    con.execute("CREATE OR REPLACE TABLE raw.lnc_clusters AS SELECT * FROM df_view").fetchall()
    con.unregister("df_view")
    n, k = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT cluster_rep) FROM raw.lnc_clusters"
    ).fetchall()[0]
    con.close()
    print(f"raw.lnc_clusters: {n:,} genes in {k:,} clusters")


if __name__ == "__main__":
    main()
