"""How many miRNAs reached the tissue atlas, and which ones did not.

Run after `dbt build` to confirm the arm-stripping rule recovered the single-arm names without
creating an ambiguous merge.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/spongescope.duckdb"))
    args = ap.parse_args()

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        total = con.execute("select count(*) from marts.dim_mirna").fetchall()[0][0]
        print(f"modeled miRNAs: {total:,}\n")

        print("match_type:")
        for row in con.execute(
            "select match_type, count(*) from intermediate.int_mirna_name_map group by 1 order by 2 desc"
        ).fetchall():
            print(f"  {row[0]:14s} {row[1]:5,}  ({row[1] / total:5.1%})")

        unmatched = con.execute(
            "select count(*) from marts.dim_mirna m "
            "where not exists (select 1 from intermediate.int_mirna_name_map n where n.mimat_id = m.mimat_id)"
        ).fetchall()[0][0]
        print(f"  {'unmatched':14s} {unmatched:5,}  ({unmatched / total:5.1%})")

        print("\nunmatched examples (first 15):")
        for row in con.execute(
            "select m.mirna_name from marts.dim_mirna m "
            "where not exists (select 1 from intermediate.int_mirna_name_map n where n.mimat_id = m.mimat_id) "
            "order by m.mirna_name limit 15"
        ).fetchall():
            print(f"  {row[0]}")

        print("\ncoexpr usability (NULL = fewer than 3 shared organs, or a flat profile):")
        row = con.execute(
            "select count(*), count(coexpr), avg(n_shared_organs) from marts.fct_pair_tissue_features"
        ).fetchall()[0]
        print(f"  {row[1]:,} of {row[0]:,} pairs have a usable correlation ({row[1] / row[0]:.1%})")
        print(f"  mean shared organs: {row[2]:.1f}")

        print("\npairs reaching the atlas:")
        for row in con.execute(
            "select mirna_atlas_known, count(*), avg(n_shared_organs) "
            "from marts.fct_pair_tissue_features group by 1 order by 1"
        ).fetchall():
            print(f"  atlas_known={row[0]!s:5s} pairs={row[1]:7,}  mean shared organs={row[2]:.1f}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
