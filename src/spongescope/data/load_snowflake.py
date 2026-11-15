"""Copy the DuckDB `raw` schema into Snowflake, so the same dbt models can run on both.

Raw data does not go through dbt -- dbt transforms what is already in the warehouse. This is the
loader that puts it there.

Three things it handles that a plain copy would not:

1. **Identifier case.** Snowflake folds unquoted names to upper case, and dbt-snowflake does not
   quote identifiers, so a column written as `"miRNAid"` would need `"miRNAid"` forever in every
   model. Instead every name is normalized to lower-case snake_case and written **unquoted**, so
   Snowflake stores it upper case and plain `select mirnaid` binds. The mapping is printed, since
   any model that referenced the original name has to be updated to match.

2. **The wide atlas.** Snowflake's UNPIVOT needs an explicit column list and the atlas is 2,660
   columns wide, so it is reshaped to long here (in pandas) and written as
   `mirna_tissue_atlas_long`. On Snowflake, `stg_mirna_tissue_atlas` then just selects from it.

3. **Idempotence.** Every table is replaced, so a failed run can simply be re-run.

Usage:
    uv run python -m spongescope.data.load_snowflake --dry-run
    uv run python -m spongescope.data.load_snowflake
    uv run python -m spongescope.data.load_snowflake --only gtex_median_tpm
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

if TYPE_CHECKING:
    from snowflake.connector import SnowflakeConnection

ATLAS_TABLE = "mirna_tissue_atlas"
# Everything in the wide atlas that is NOT a miRNA. "index" is a pandas artefact in the raw
# download; the DuckDB model excludes it from the unpivot, so it is dropped here too.
# Compared against normalize(), so these are upper case.
ATLAS_ID_COLS = {"INDEX", "BIOTYPE", "ORGAN_SYSTEM", "TISSUE", "METRIC"}
ATLAS_DROP_COLS = {"INDEX"}
REQUIRED_ENV = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_PATH"]


def normalize(name: str) -> str:
    """snake_case, then UPPER CASE, written quoted.

    Uppercase-and-quoted rather than lowercase-and-unquoted, because several raw columns are
    Snowflake reserved words -- ENCORI has `start` and `end` -- and an unquoted reserved word is a
    syntax error in DDL, not just in queries. Quoting sidesteps reserved words entirely, and
    uppercase is what Snowflake would have stored for an unquoted name anyway, so a plain
    `select gene_id` in a model still binds. The two choices only work together: quoted lowercase
    would NOT match an unquoted reference.
    """
    out = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").upper()
    if not out:
        raise ValueError(f"column name {name!r} normalizes to nothing")
    if out[0].isdigit():
        out = f"C_{out}"
    return out


def normalize_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    mapping = {c: normalize(c) for c in df.columns}
    changed = {k: v for k, v in mapping.items() if k != v}
    dupes = [v for v in set(mapping.values()) if list(mapping.values()).count(v) > 1]
    if dupes:
        raise ValueError(f"column names collide after normalization: {sorted(dupes)}")
    return df.rename(columns=mapping), changed


def reshape_atlas(df: pd.DataFrame) -> pd.DataFrame:
    """Wide (one column per miRNA) -> long (mirna_name, expr_value), matching the DuckDB UNPIVOT.

    Reshaping happens BEFORE any name normalization, and the miRNA column names are carried into
    `mirna_name` **verbatim**. That matters: on DuckDB the staging model gets these names from
    UNPIVOT, so they keep their original form ("hsa-miR-99a-5p"), and `int_mirna_name_map` joins
    on exactly that string. Normalizing first would write "hsa_mir_99a_5p" and the join would
    silently return zero rows on Snowflake only.

    Only the id columns are renamed, and they are renamed to the names the model expects.
    """
    id_cols = [c for c in df.columns if normalize(c) in ATLAS_ID_COLS]
    if not id_cols:
        id_cols = [c for c in df.columns if df[c].dtype == object]
        print(f"  no known id columns; falling back to object-dtype columns: {id_cols}")
    value_cols = [c for c in df.columns if c not in id_cols]
    print(f"  reshaping {len(df):,} x {len(df.columns):,} -> long on {len(value_cols):,} miRNAs")
    print(f"  id columns: {id_cols}")
    print(f"  miRNA names kept verbatim, e.g. {value_cols[:3]}")

    long = df.melt(
        id_vars=id_cols, value_vars=value_cols, var_name="MIRNA_NAME", value_name="EXPR_VALUE"
    )
    long["EXPR_VALUE"] = pd.to_numeric(long["EXPR_VALUE"], errors="coerce")
    long = long[long["EXPR_VALUE"].notna()]

    # DuckDB's UNPIVOT drops NULL measurements unless INCLUDE NULLS is given, so dropping them
    # here is what keeps the two row counts equal.
    keep = {c: normalize(c) for c in id_cols if normalize(c) not in ATLAS_DROP_COLS}
    long = long.rename(columns=keep)
    return long[[*keep.values(), "MIRNA_NAME", "EXPR_VALUE"]].reset_index(drop=True)


def raw_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "select table_name from information_schema.tables "
        "where lower(table_schema) = 'raw' order by table_name"
    ).fetchall()
    return [r[0] for r in rows]


def load_private_key() -> bytes:
    """Read the PKCS#8 private key and hand it to the connector as DER bytes."""
    from cryptography.hazmat.primitives import serialization

    path = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])
    if not path.exists():
        sys.exit(f"private key not found: {path}\nGenerate it with scripts/snowflake_keypair.py")
    raw = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    key = serialization.load_pem_private_key(
        path.read_bytes(), password=raw.encode() if raw else None
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def connect_snowflake() -> SnowflakeConnection:
    """Key-pair authentication.

    Snowflake finished deprecating single-factor password login in October 2026: a human user
    needs MFA on every password sign-in, which would mean an MFA push per connection, and a
    SERVICE user cannot hold a password at all. So there is no password path here.
    """
    import snowflake.connector

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        sys.exit(
            f"missing environment variable(s): {', '.join(missing)}\n"
            "See SNOWFLAKE_KEYPAIR.md -- programmatic access needs a key pair, not a password."
        )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=load_private_key(),
        role=os.environ.get("SNOWFLAKE_ROLE", "SPONGESCOPE_ROLE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "SPONGESCOPE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "SPONGESCOPE"),
        schema="RAW",
        client_session_keep_alive=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/spongescope.duckdb"))
    ap.add_argument("--only", nargs="*", default=None, help="load just these raw tables")
    ap.add_argument("--skip", nargs="*", default=[], help="skip these raw tables")
    ap.add_argument("--dry-run", action="store_true", help="report what would be loaded, no writes")
    ap.add_argument("--chunk-size", type=int, default=250_000)
    args = ap.parse_args()

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        tables = raw_tables(con)
        if args.only:
            tables = [t for t in tables if t in set(args.only)]
        tables = [t for t in tables if t not in set(args.skip)]
        if not tables:
            sys.exit("no matching raw tables")

        print(f"{len(tables)} raw table(s) to load: {', '.join(tables)}\n")

        if args.dry_run:
            for t in tables:
                n = con.execute(f'select count(*) from raw."{t}"').fetchall()[0][0]
                cols = list(con.execute(f'select * from raw."{t}" limit 0').df().columns)
                if t == ATLAS_TABLE:
                    id_cols = [c for c in cols if normalize(c) in ATLAS_ID_COLS]
                    mirnas = [c for c in cols if c not in id_cols]
                    print(f"  {t}: {n:,} rows, {len(cols):,} cols -> RAW.{t.upper()}_LONG")
                    print(f"      reshaped to long on {len(mirnas):,} miRNA columns")
                    print(f"      id columns {id_cols} -> {[normalize(c) for c in id_cols]}")
                    print(
                        f"      dropped: {sorted(ATLAS_DROP_COLS & {normalize(c) for c in cols})}"
                    )
                    print(
                        "      miRNA names become values in mirna_name, kept verbatim "
                        f"(e.g. {mirnas[:2]})"
                    )
                    continue
                _, changed = normalize_frame(pd.DataFrame(columns=cols))
                print(f"  {t}: {n:,} rows, {len(cols):,} cols -> RAW.{t.upper()}")
                for old, new in changed.items():
                    print(f"      rename {old!r} -> {new!r}")
            print("\ndry run; nothing written")
            return

        import snowflake.connector.errors
        from snowflake.connector.pandas_tools import write_pandas

        sf = connect_snowflake()
        cur = sf.cursor()
        database = os.environ.get("SNOWFLAKE_DATABASE", "SPONGESCOPE")
        warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "SPONGESCOPE_WH")
        # No account-level DDL here. The warehouse and database are created once by an admin
        # (see SNOWFLAKE_KEYPAIR.md); a service role deliberately has neither CREATE WAREHOUSE
        # nor CREATE DATABASE, and `create ... if not exists` still requires the privilege even
        # when the object already exists. The loader only uses what it was granted, and creates
        # the RAW schema, which it does own.
        for stmt in (
            f"use warehouse {warehouse}",
            f"use database {database}",
            f"create schema if not exists {database}.raw",
            f"use schema {database}.raw",
        ):
            try:
                cur.execute(stmt)
            except snowflake.connector.errors.ProgrammingError as exc:
                sys.exit(
                    f"failed on: {stmt}\n{exc}\n\n"
                    "This is a grant, not a connection problem. The setup SQL in "
                    "SNOWFLAKE_KEYPAIR.md creates the warehouse and database as ACCOUNTADMIN and "
                    "grants them to SPONGESCOPE_ROLE; run it, then retry."
                )

        for t in tables:
            n = con.execute(f'select count(*) from raw."{t}"').fetchall()[0][0]
            print(f"{t}: {n:,} rows")
            df = con.execute(f'select * from raw."{t}"').df()

            if t == ATLAS_TABLE:
                # Reshape first; see reshape_atlas for why normalizing first would be wrong.
                df = reshape_atlas(df)
                target = f"{t}_long"
                print(f"  -> {len(df):,} long rows")
            else:
                target = t
                df, changed = normalize_frame(df)
                for old, new in changed.items():
                    print(f"  rename {old!r} -> {new!r}")

            ok, nchunks, nrows, _ = write_pandas(
                sf,
                df,
                table_name=target.upper(),
                database=database,
                schema="RAW",
                auto_create_table=True,
                overwrite=True,
                # Quoted, with the names already upper-cased by normalize(): see its docstring.
                quote_identifiers=True,
                chunk_size=args.chunk_size,
            )
            if not ok:
                sys.exit(f"write_pandas failed for {target}")
            print(f"  wrote RAW.{target.upper()}: {nrows:,} rows in {nchunks} chunk(s)\n")

        print("verifying row counts in Snowflake:")
        for t in tables:
            target = f"{t}_long" if t == ATLAS_TABLE else t
            got = cur.execute(f"select count(*) from {database}.raw.{target}").fetchone()[0]
            print(f"  RAW.{target.upper():40s} {got:>12,}")
        cur.close()
        sf.close()
    finally:
        con.close()


if __name__ == "__main__":
    main()
