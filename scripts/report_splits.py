"""Summarize the cold-start splits in marts.fct_pairs."""

from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "data" / "spongescope.duckdb"

SQL = """
WITH summary AS (
    SELECT
        split,
        COALESCE(eval_group, '-')        AS eval_group,
        COUNT(DISTINCT gene_id)          AS lncrnas,
        COUNT(DISTINCT cluster_id)       AS clusters,
        COUNT(DISTINCT mimat_id)         AS mirnas,
        SUM(label)                       AS positives,
        COUNT(*) - SUM(label)            AS negatives
    FROM marts.fct_pairs
    GROUP BY split, COALESCE(eval_group, '-')
)
SELECT
    split, eval_group, lncrnas, clusters, mirnas, positives, negatives,
    ROUND(negatives * 1.0 / positives, 2) AS neg_per_pos
FROM summary
ORDER BY CASE split WHEN 'train' THEN 1 WHEN 'val' THEN 2 ELSE 3 END, eval_group
"""

EXTRA = {
    "pairs dropped (held-out miRNA in train/val)": """
        SELECT (SELECT COUNT(*) FROM intermediate.int_positive_pairs)
             + (SELECT COUNT(*) FROM intermediate.int_negative_pairs)
             - (SELECT COUNT(*) FROM marts.fct_pairs)""",
    "held-out miRNAs (seed families)": """
        SELECT COUNT(*) || ' (' || COUNT(DISTINCT seed) || ')'
        FROM marts.dim_mirna WHERE is_holdout""",
    "clusters / largest cluster (genes)": """
        SELECT COUNT(DISTINCT cluster_id) || ' / ' || MAX(cluster_size) FROM marts.dim_lncrna""",
}

con = duckdb.connect(str(DB), read_only=True)
cur = con.execute(SQL)
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
print(" | ".join(f"{c:>11}" for c in cols))
for r in rows:
    print(" | ".join(f"{v!s:>11}" for v in r))
print()
for label, sql in EXTRA.items():
    print(f"{label:<45} {con.execute(sql).fetchall()[0][0]}")
con.close()
