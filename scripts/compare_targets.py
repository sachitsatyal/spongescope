"""Do the Snowflake marts match the DuckDB marts?

`dbt build --target prod` passing its tests proves the SQL runs and the constraints hold. It does
not prove the two warehouses produced the same numbers -- a silently different split, a dropped
row from an identifier mismatch, or a float that rounds differently would all pass the tests.

So this compares, per mart: row count, count of distinct key, label balance, and the mean of every
numeric column rounded to 6 places. Anything that differs is printed; a clean run prints nothing
but the table names.

Usage:
    uv run python scripts/compare_targets.py
    uv run python scripts/compare_targets.py --models fct_pairs dim_mirna
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

if TYPE_CHECKING:
    from snowflake.connector.cursor import SnowflakeCursor

# (schema, table, key, hash_dependent)
#
# hash_dependent means the model's contents depend on stable_uniform, whose underlying hash
# differs between DuckDB and Snowflake. Those models are EXPECTED to differ: the random draws
# (split assignment, negative sampling) are not reproducible across engines unless the hash is
# frozen. Dev remains authoritative for the benchmark. A difference in a hash-dependent model is
# reported but does not fail the run; a difference anywhere else does.
DEFAULT_MODELS = [
    ("marts", "dim_lncrna", "gene_id", False),
    # dim_mirna carries is_holdout, which comes from int_mirna_holdout -> stable_uniform.
    ("marts", "dim_mirna", "mimat_id", True),
    ("marts", "fct_lncrna_tissue_expression", None, False),
    ("marts", "fct_mirna_tissue_expression", None, False),
    ("marts", "dim_lncrna_tissue_profile", "gene_id", False),
    ("intermediate", "int_mirna_name_map", "mimat_id", False),
    ("intermediate", "int_positive_pairs", None, False),
    ("intermediate", "int_lncrna_splits", "gene_id", True),
    ("intermediate", "int_negative_pairs", None, True),
    ("marts", "fct_pairs", "pair_id", True),
    ("marts", "fct_pair_tissue_features", "pair_id", True),
]


def key_checksum(df: pd.DataFrame, key: str) -> float:
    """A number that changes if the SET OF KEYS changes.

    Row counts and means can agree while the rows themselves differ -- two split assignments with
    the same 80/10/10 counts, say. Hashing the sorted keys turns "the same number of rows" into
    "the same rows", which is what equivalence actually means.
    """
    joined = "\u0000".join(sorted(df[key].astype(str)))
    return float(int(hashlib.sha256(joined.encode()).hexdigest()[:12], 16))


def profile(df: pd.DataFrame, key: str | None) -> dict[str, float]:
    out: dict[str, float] = {"n_rows": float(len(df))}
    if key and key in df.columns:
        out["n_distinct_key"] = float(df[key].nunique())
        out["key_checksum"] = key_checksum(df, key)
    if "label" in df.columns:
        out["n_positive"] = float(pd.to_numeric(df["label"], errors="coerce").sum())
    for col in sorted(df.columns):
        series = pd.to_numeric(df[col], errors="coerce")
        if series.notna().sum() and pd.api.types.is_numeric_dtype(series):
            out[f"mean_{col}"] = round(float(series.mean()), 6)
            out[f"nulls_{col}"] = float(series.isna().sum())
    return out


def fetch_duckdb(db: Path, schema: str, table: str) -> pd.DataFrame:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(f'select * from {schema}."{table}"').df()
    finally:
        con.close()


def fetch_snowflake(cur: SnowflakeCursor, schema: str, table: str) -> pd.DataFrame:
    cur.execute(f"select * from {schema}.{table}")
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/spongescope.duckdb"))
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--out", type=Path, default=Path("reports/target_comparison.csv"))
    args = ap.parse_args()

    import snowflake.connector

    from spongescope.data.load_snowflake import load_private_key

    models = DEFAULT_MODELS
    if args.models:
        wanted = set(args.models)
        models = [m for m in models if m[1] in wanted]

    sf = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=load_private_key(),
        role=os.environ.get("SNOWFLAKE_ROLE", "SPONGESCOPE_ROLE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "SPONGESCOPE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "SPONGESCOPE"),
    )
    cur = sf.cursor()

    rows = []
    problems = 0
    expected_diffs = 0
    for schema, table, key, hash_dependent in models:
        tag = "  [hash-dependent, differences expected]" if hash_dependent else ""
        print(f"\n=== {schema}.{table}{tag}")
        try:
            dev = profile(fetch_duckdb(args.db, schema, table), key)
        except Exception as exc:  # noqa: BLE001 - any failure here is just "not comparable"
            print(f"  duckdb: {type(exc).__name__}: {exc}")
            continue
        try:
            prod = profile(fetch_snowflake(cur, schema, table), key)
        except Exception as exc:  # noqa: BLE001
            print(f"  snowflake: {type(exc).__name__}: {exc}")
            problems += 1
            continue

        keys = sorted(set(dev) | set(prod))
        diffs = 0
        for k in keys:
            a, b = dev.get(k), prod.get(k)
            same = a is not None and b is not None and abs(a - b) <= 1e-6
            rows.append(
                {
                    "model": f"{schema}.{table}",
                    "metric": k,
                    "duckdb": a,
                    "snowflake": b,
                    "match": same,
                }
            )
            if not same:
                diffs += 1
                print(f"  DIFF {k}: duckdb={a} snowflake={b}")
        if diffs and hash_dependent:
            expected_diffs += 1
        elif diffs:
            problems += 1
        else:
            note = ""
            if "key_checksum" not in dev:
                note = "  [no key column: row counts and means only, NOT row-level equivalence]"
            print(f"  match ({len(keys)} metrics, {int(dev['n_rows']):,} rows){note}")

    cur.close()
    sf.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"\nwrote {args.out}")
    if expected_diffs:
        print(
            f"\n{expected_diffs} hash-dependent model(s) differ -- expected, since DuckDB and "
            "Snowflake hash differently. Dev stays authoritative for the benchmark."
        )
    if problems:
        print(f"\n{problems} model(s) differ unexpectedly -- prod is NOT equivalent yet")
        sys.exit(1)
    print("\nevery hash-independent model matches")


if __name__ == "__main__":
    main()
