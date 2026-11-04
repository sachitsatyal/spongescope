"""Export the marts to Parquet in data/processed/ for the training code (Phase 3+)."""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "spongescope.duckdb"
OUT = ROOT / "data" / "processed"

TABLES = ["fct_pairs", "dim_lncrna", "dim_mirna"]

OUT.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(DB), read_only=True)
for t in TABLES:
    path = (OUT / f"{t}.parquet").as_posix()
    con.execute(f"COPY (SELECT * FROM marts.{t}) TO '{path}' (FORMAT parquet)").fetchall()
    n = con.execute(f"SELECT COUNT(*) FROM marts.{t}").fetchall()[0][0]
    print(f"{t:<12} {n:>9,} rows -> {path}")
con.close()
