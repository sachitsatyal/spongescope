"""Inspect the miRNATissueAtlas 2025 per-tissue file and load it raw into DuckDB.

Prints its layout so the staging model (step 3.2) can be written against real columns.
"""

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "raw" / "mirna_tissue_atlas" / "mirna_avg_std_human.parquet"
DB = ROOT / "data" / "spongescope.duckdb"

head = PATH.read_bytes()[:4]
print(f"file: {PATH.name}  size: {PATH.stat().st_size / 1e6:.1f} MB  magic: {head!r}")
if head != b"PAR1":
    print("Not a Parquet file. First 300 bytes:")
    print(PATH.read_bytes()[:300])
    raise SystemExit(1)

df = pd.read_parquet(PATH)
print(f"shape: {df.shape}")
print(f"index: name={df.index.name!r} dtype={df.index.dtype} first={list(df.index[:5])}")
print(f"columns ({len(df.columns)}), first 15: {list(df.columns[:15])}")
print(f"last 5 columns: {list(df.columns[-5:])}")
print(df.iloc[:3, :8].to_string())

df = df.reset_index()
df.columns = [str(c) for c in df.columns]
con = duckdb.connect(str(DB))
con.execute("CREATE SCHEMA IF NOT EXISTS raw").fetchall()
con.register("df_view", df)
con.execute("CREATE OR REPLACE TABLE raw.mirna_tissue_atlas AS SELECT * FROM df_view").fetchall()
con.unregister("df_view")
n = con.execute("SELECT COUNT(*) FROM raw.mirna_tissue_atlas").fetchall()[0][0]
con.close()
print(f"loaded raw.mirna_tissue_atlas: {n:,} rows")
