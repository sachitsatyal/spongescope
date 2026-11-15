"""Dump the GTEx and miRNATissueAtlas vocabularies, so the tissue mapping can be written
against real names rather than guessed ones. Also diagnoses the unmatched miRNA names.

  uv run python scripts\\list_tissues.py
"""

from pathlib import Path

import duckdb
import pandas as pd

DB = Path(__file__).resolve().parents[1] / "data" / "spongescope.duckdb"
con = duckdb.connect(str(DB), read_only=True)


def q(sql: str) -> pd.DataFrame:
    return con.execute(sql).fetch_df()


print("=" * 78)
print("GTEx tissues (lncRNA expression)")
print("=" * 78)
g = q("""
    SELECT tissue, COUNT(*) AS n_genes,
           SUM(CASE WHEN is_expressed THEN 1 ELSE 0 END) AS n_expressed
    FROM marts.fct_lncrna_tissue_expression GROUP BY tissue ORDER BY tissue
""")
print(f"{len(g)} tissues")
for _, r in g.iterrows():
    print(f"  {r.tissue:<45} expressed {int(r.n_expressed):>5} / {int(r.n_genes)}")

print()
print("=" * 78)
print("miRNATissueAtlas contexts")
print("=" * 78)
a = q("""
    SELECT biotype, organ_system, tissue, COUNT(DISTINCT mimat_id) AS n_mirna
    FROM marts.fct_mirna_tissue_expression GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
""")
for bt, grp in a.groupby("biotype"):
    print(f"\n--- biotype = {bt}  ({len(grp)} contexts) ---")
    for _, r in grp.iterrows():
        print(f"  {r.organ_system:<28} / {r.tissue:<32} n_miRNA {int(r.n_mirna)}")

print()
print("=" * 78)
print("miRNA name matching (dim_mirna -> atlas)")
print("=" * 78)
mir = q("SELECT mimat_id, mirna_name FROM marts.dim_mirna")
atlas_names = set(q("SELECT DISTINCT mirna_name FROM staging.stg_mirna_tissue_atlas").mirna_name)
matched = mir.mirna_name.isin(atlas_names)
print(f"dim_mirna                {len(mir)}")
print(f"atlas distinct names     {len(atlas_names)}")
print(f"matched exactly          {int(matched.sum())} ({matched.mean():.1%})")

unmatched = mir.loc[~matched, "mirna_name"].tolist()
print(f"unmatched                {len(unmatched)}")
print("examples:", ", ".join(unmatched[:15]))

lower = {n.lower(): n for n in atlas_names}
by_lower = [n for n in unmatched if n.lower() in lower]
no_arm = {n.rsplit("-", 1)[0].lower() for n in atlas_names if n.endswith(("-5p", "-3p"))}
by_no_arm = [n for n in unmatched if n.rsplit("-", 1)[0].lower() in no_arm]
print(f"would match ignoring case          {len(by_lower)}")
print(
    f"share an atlas stem ignoring arm   {len(by_no_arm)}  "
    f"(ambiguous: -5p and -3p differ biologically, so NOT a safe merge)"
)
print("\nunmatched, full list:")
for i in range(0, len(unmatched), 6):
    print("  " + ", ".join(unmatched[i : i + 6]))
con.close()
