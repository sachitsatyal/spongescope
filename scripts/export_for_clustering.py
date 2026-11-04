"""Export representative transcripts of all positive lncRNA genes to FASTA for MMseqs2.

Output: data/interim/clustering/lncrna_representatives.fa  (upload this to Colab)
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "spongescope.duckdb"
OUT = ROOT / "data" / "interim" / "clustering" / "lncrna_representatives.fa"

SQL = """
SELECT r.gene_id, r.sequence
FROM intermediate.int_gene_representative AS r
WHERE r.gene_id IN (SELECT DISTINCT gene_id FROM intermediate.int_positive_pairs)
ORDER BY r.gene_id
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(DB), read_only=True)
rows = con.execute(SQL).fetchall()
con.close()

with OUT.open("w", newline="\n") as fh:
    for gene_id, seq in rows:
        fh.write(f">{gene_id}\n")
        for i in range(0, len(seq), 80):
            fh.write(seq[i : i + 80] + "\n")

print(f"Wrote {len(rows):,} sequences to {OUT}")
