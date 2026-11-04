"""Summarize the Phase 2.2 intermediate tables."""

from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "data" / "spongescope.duckdb"

CHECKS = {
    "eligible transcripts": "SELECT COUNT(*) FROM intermediate.int_lncrna_transcripts",
    "representative genes": "SELECT COUNT(*) FROM intermediate.int_gene_representative",
    "ENCORI sites matched to a transcript (%)": """
        SELECT ROUND(100.0 * COUNT(DISTINCT CASE WHEN transcript_id IS NOT NULL THEN site_id END)
                     / COUNT(DISTINCT site_id), 1)
        FROM intermediate.int_site_transcript_hits""",
    "positive pairs": "SELECT COUNT(*) FROM intermediate.int_positive_pairs",
    "positive lncRNA genes": "SELECT COUNT(DISTINCT gene_id) FROM intermediate.int_positive_pairs",
    "positive miRNAs": "SELECT COUNT(DISTINCT mimat_id) FROM intermediate.int_positive_pairs",
    "positives with a site on the chosen transcript (%)": """
        SELECT ROUND(100.0 * AVG(CASE WHEN n_sites_on_transcript > 0 THEN 1 ELSE 0 END), 1)
        FROM intermediate.int_positive_pairs""",
    "negative pairs (degree_matched / random)": """
        SELECT SUM(CASE WHEN pair_type = 'degree_matched' THEN 1 ELSE 0 END) || ' / ' ||
               SUM(CASE WHEN pair_type = 'random' THEN 1 ELSE 0 END)
        FROM intermediate.int_negative_pairs""",
    "overall negative:positive ratio": """
        SELECT ROUND((SELECT COUNT(*) FROM intermediate.int_negative_pairs) * 1.0
                     / (SELECT COUNT(*) FROM intermediate.int_positive_pairs), 2)""",
    "lncRNA genes below the target ratio": """
        SELECT COUNT(*) FROM (
            SELECT p.gene_id, p.n_pos, COALESCE(n.n_neg, 0) AS n_neg
            FROM (SELECT gene_id, COUNT(*) n_pos FROM intermediate.int_positive_pairs
                  GROUP BY 1) p
            LEFT JOIN (SELECT gene_id, COUNT(*) n_neg FROM intermediate.int_negative_pairs
                       GROUP BY 1) n USING (gene_id)
        ) WHERE n_neg < 10 * n_pos""",
}

con = duckdb.connect(str(DB), read_only=True)
for label, sql in CHECKS.items():
    print(f"{label:<52} {con.execute(sql).fetchall()[0][0]}")
con.close()
