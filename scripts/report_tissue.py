"""Summarize tissue expression for modeled lncRNAs (GTEx v10) and miRNAs (miRNATissueAtlas)."""

from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "data" / "spongescope.duckdb"

LNC = {
    "modeled lncRNAs": "SELECT COUNT(*) FROM marts.dim_lncrna",
    "lncRNAs found in GTEx (%)": """
        SELECT ROUND(100.0 * COUNT(DISTINCT e.gene_id) / (SELECT COUNT(*) FROM marts.dim_lncrna), 1)
        FROM marts.fct_lncrna_tissue_expression e""",
    "GTEx tissues": "SELECT COUNT(DISTINCT tissue) FROM marts.fct_lncrna_tissue_expression",
    "median tissues where expressed (TPM >= 1)": """
        SELECT MEDIAN(n_expressed_tissues) FROM marts.dim_lncrna_tissue_profile""",
    "median tissue specificity tau (0 = broad, 1 = one tissue)": """
        SELECT ROUND(MEDIAN(tau), 3) FROM marts.dim_lncrna_tissue_profile""",
    "lncRNAs expressed in no tissue": """
        SELECT COUNT(*) FROM marts.dim_lncrna_tissue_profile WHERE n_expressed_tissues = 0""",
}

MIR = {
    "modeled miRNAs": "SELECT COUNT(*) FROM marts.dim_mirna",
    "miRNAs found in atlas (%)": """
        SELECT ROUND(100.0 * COUNT(DISTINCT mimat_id) / (SELECT COUNT(*) FROM marts.dim_mirna), 1)
        FROM marts.fct_mirna_tissue_expression""",
    "atlas contexts (biotype/organ/tissue)": """
        SELECT COUNT(*) FROM (SELECT DISTINCT biotype, organ_system, tissue
                              FROM marts.fct_mirna_tissue_expression)""",
    "median of mean expression": """
        SELECT ROUND(MEDIAN(mean_expr), 2) FROM marts.fct_mirna_tissue_expression""",
}

con = duckdb.connect(str(DB), read_only=True)
print("== lncRNA (GTEx v10) ==")
for label, sql in LNC.items():
    print(f"{label:<58} {con.execute(sql).fetchall()[0][0]}")
print("\nTop GTEx tissues by number of expressed lncRNAs:")
for t, n in con.execute(
    """SELECT tissue, SUM(CASE WHEN is_expressed THEN 1 ELSE 0 END) AS n
       FROM marts.fct_lncrna_tissue_expression GROUP BY tissue ORDER BY n DESC LIMIT 5"""
).fetchall():
    print(f"  {t:<45} {n}")

print("\n== miRNA (miRNATissueAtlas 2025) ==")
for label, sql in MIR.items():
    print(f"{label:<58} {con.execute(sql).fetchall()[0][0]}")
print("\nContexts per biotype:")
for b, n in con.execute(
    """SELECT biotype, COUNT(DISTINCT organ_system || '|' || tissue) AS n
       FROM marts.fct_mirna_tissue_expression GROUP BY biotype ORDER BY n DESC"""
).fetchall():
    print(f"  {b!s:<45} {n}")
print("\nSample tissue names (biotype = first above):")
rows = con.execute(
    """WITH b AS (SELECT biotype FROM marts.fct_mirna_tissue_expression
                  GROUP BY biotype ORDER BY COUNT(DISTINCT tissue) DESC LIMIT 1)
       SELECT DISTINCT organ_system, tissue FROM marts.fct_mirna_tissue_expression
       WHERE biotype = (SELECT biotype FROM b) ORDER BY 1, 2 LIMIT 25"""
).fetchall()
for o, t in rows:
    print(f"  {o} / {t}")
con.close()
