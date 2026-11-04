"""Load raw downloads into DuckDB (schema: raw)."""

from __future__ import annotations

import gzip
from pathlib import Path

import duckdb
import pandas as pd
from Bio import SeqIO

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "spongescope.duckdb"


def open_text(path: Path):
    return gzip.open(path, "rt") if path.suffix == ".gz" else path.open()


def to_rna(seq: str) -> str:
    return seq.upper().replace("T", "U")


def load_lncrna() -> pd.DataFrame:
    # GENCODE header: transcript_id|gene_id|havana_gene|havana_tx|tx_name|gene_name|length|biotype|
    path = next((RAW / "gencode").glob("*.lncRNA_transcripts.fa.gz"))
    rows = []
    with open_text(path) as fh:
        for rec in SeqIO.parse(fh, "fasta"):
            f = rec.id.split("|")
            seq = to_rna(str(rec.seq))
            rows.append(
                {
                    "transcript_id": f[0],
                    "gene_id": f[1],
                    "transcript_name": f[4],
                    "gene_name": f[5],
                    "length": len(seq),
                    "sequence": seq,
                }
            )
    return pd.DataFrame(rows)


def load_mirna() -> pd.DataFrame:
    # miRBase header: >hsa-let-7a-5p MIMAT0000062 Homo sapiens let-7a-5p
    rows = []
    with open_text(RAW / "mirbase" / "mature.fa") as fh:
        for rec in SeqIO.parse(fh, "fasta"):
            if not rec.id.startswith("hsa-"):
                continue
            seq = to_rna(str(rec.seq))
            rows.append(
                {
                    "mirna_name": rec.id,
                    "mimat_id": rec.description.split()[1],
                    "length": len(seq),
                    "sequence": seq,
                }
            )
    return pd.DataFrame(rows)


def load_encori() -> pd.DataFrame:
    path = RAW / "encori" / "encori_hg38_mirna_lncrna_clip1.tsv"
    df = pd.read_csv(path, sep="\t", comment="#", low_memory=False)
    if "miRNAname" not in df.columns:
        raise ValueError(f"ENCORI file looks wrong. Columns: {list(df.columns)[:5]}")
    return df


def load_gtex() -> pd.DataFrame:
    path = next((RAW / "gtex").glob("*gene_median_tpm.gct.gz"))
    wide = pd.read_csv(path, sep="\t", skiprows=2)
    wide = wide.rename(
        columns={"Name": "gene_id_versioned", "Description": "gene_name"}
    )
    wide["gene_id"] = wide["gene_id_versioned"].str.split(".").str[0]
    return wide.melt(
        id_vars=["gene_id", "gene_id_versioned", "gene_name"],
        var_name="tissue",
        value_name="median_tpm",
    )


def run(con: duckdb.DuckDBPyConnection, sql: str) -> list:
    """Execute and fully consume the result (required by DuckDB 2.x)."""
    return con.execute(sql).fetchall()


def main() -> None:
    tables = {
        "lncrna_transcripts": load_lncrna(),
        "mirna_mature": load_mirna(),
        "encori_mirna_lncrna": load_encori(),
        "gtex_median_tpm": load_gtex(),
    }
    con = duckdb.connect(str(DB))
    run(con, "CREATE SCHEMA IF NOT EXISTS raw")
    for name, df in tables.items():
        con.register("df_view", df)
        run(con, f"CREATE OR REPLACE TABLE raw.{name} AS SELECT * FROM df_view")
        con.unregister("df_view")
        n = run(con, f"SELECT COUNT(*) FROM raw.{name}")[0][0]
        print(f"raw.{name:<22} {n:>12,} rows")
    con.close()


if __name__ == "__main__":
    main()
