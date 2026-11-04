"""Sanity checks on the raw DuckDB tables."""

from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "data" / "spongescope.duckdb"

CHECKS = {
    "ENCORI unique (gene, miRNA) pairs": """
        SELECT COUNT(*) FROM (SELECT DISTINCT geneID, miRNAname FROM raw.encori_mirna_lncrna)""",
    "ENCORI unique lncRNA genes": "SELECT COUNT(DISTINCT geneID) FROM raw.encori_mirna_lncrna",
    "ENCORI unique miRNAs": "SELECT COUNT(DISTINCT miRNAname) FROM raw.encori_mirna_lncrna",
    "ENCORI genes found in GENCODE 50 (%)": """
        SELECT ROUND(100.0 * AVG(CASE WHEN g.gene_id IS NOT NULL THEN 1 ELSE 0 END), 1)
        FROM (SELECT DISTINCT geneID FROM raw.encori_mirna_lncrna) e
        LEFT JOIN (SELECT DISTINCT split_part(gene_id, '.', 1) AS gene_id
                   FROM raw.lncrna_transcripts) g ON e.geneID = g.gene_id""",
    "ENCORI miRNAs found in miRBase (%)": """
        SELECT ROUND(100.0 * AVG(CASE WHEN m.mirna_name IS NOT NULL THEN 1 ELSE 0 END), 1)
        FROM (SELECT DISTINCT miRNAname FROM raw.encori_mirna_lncrna) e
        LEFT JOIN raw.mirna_mature m ON e.miRNAname = m.mirna_name""",
    "ENCORI miRNAs found in miRBase by MIMAT (%)": """
        SELECT ROUND(100.0 * AVG(CASE WHEN m.mimat_id IS NOT NULL THEN 1 ELSE 0 END), 1)
        FROM (SELECT DISTINCT miRNAid FROM raw.encori_mirna_lncrna) e
        LEFT JOIN raw.mirna_mature m ON e.miRNAid = m.mimat_id""",
    "GENCODE lncRNA genes": """
        SELECT COUNT(DISTINCT split_part(gene_id, '.', 1)) FROM raw.lncrna_transcripts""",
    "lncRNA length median / max": """
        SELECT CAST(MEDIAN(length) AS INT) || ' / ' || MAX(length) FROM raw.lncrna_transcripts""",
}

con = duckdb.connect(str(DB), read_only=True)
for label, sql in CHECKS.items():
    print(f"{label:<45} {con.execute(sql).fetchall()[0][0]}")
con.close()
