"""Summarize positives, negatives by type, and seed-site rates (Phase 2.2 / 4.1)."""

from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "data" / "spongescope.duckdb"

CHECKS = {
    "positive pairs": "SELECT COUNT(*) FROM intermediate.int_positive_pairs",
    "positive lncRNA genes": "SELECT COUNT(DISTINCT gene_id) FROM intermediate.int_positive_pairs",
    "positive miRNAs": "SELECT COUNT(DISTINCT mimat_id) FROM intermediate.int_positive_pairs",
    "negative pairs": "SELECT COUNT(*) FROM intermediate.int_negative_pairs",
    "overall negative:positive ratio": """
        SELECT ROUND((SELECT COUNT(*) FROM intermediate.int_negative_pairs) * 1.0
                     / (SELECT COUNT(*) FROM intermediate.int_positive_pairs), 2)""",
}

con = duckdb.connect(str(DB), read_only=True)
for label, sql in CHECKS.items():
    print(f"{label:<40} {con.execute(sql).fetchall()[0][0]}")

print("\nnegatives by type:")
for t, n in con.execute(
    "SELECT pair_type, COUNT(*) FROM intermediate.int_negative_pairs GROUP BY 1 ORDER BY 2 DESC"
).fetchall():
    print(f"  {t:<20} {n:>9,}")

print("\nshare with a 7mer seed site (fct_pairs):")
for label, t, rate, n in con.execute(
    """SELECT label, pair_type, ROUND(AVG(CASE WHEN has_seed_site THEN 1 ELSE 0 END), 3), COUNT(*)
       FROM marts.fct_pairs GROUP BY 1, 2 ORDER BY 1 DESC, 2"""
).fetchall():
    print(f"  label {label}  {t:<16} {rate:>6}  (n={n:,})")
for label, rate in con.execute(
    """SELECT label, ROUND(AVG(CASE WHEN has_seed_site THEN 1 ELSE 0 END), 3)
       FROM marts.fct_pairs GROUP BY 1 ORDER BY 1 DESC"""
).fetchall():
    print(f"  label {label}  ALL              {rate:>6}")
con.close()
