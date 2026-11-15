"""Apply the mechanical portability edits to the dbt models.

Every edit is an exact string replacement, verified before and after: if a target string is not
found exactly once the script changes nothing and reports it, so a half-applied state is not
possible. Re-running is safe -- already-patched files are reported as such and skipped.

The two edits that are NOT mechanical are left out on purpose:
  * stg_mirna_tissue_atlas.sql  -- shipped as a full replacement (two code paths)
  * int_positive_pairs.sql L41  -- the lateral-flatten restructure needs the FROM clause

Usage:
    uv run python scripts/apply_portability_patches.py --dry-run
    uv run python scripts/apply_portability_patches.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# (relative path, [(old, new), ...])
PATCHES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "dbt/models/staging/stg_encori_sites.sql",
        [
            ('"miRNAid"', "{{ raw_col('miRNAid') }}"),
            ('"miRNAname"', "{{ raw_col('miRNAname') }}"),
            ('"geneID"', "{{ raw_col('geneID') }}"),
            ('"geneName"', "{{ raw_col('geneName') }}"),
            ('"clipExpNum"', "{{ raw_col('clipExpNum') }}"),
            ('"degraExpNum"', "{{ raw_col('degraExpNum') }}"),
            ('"RBP"', "{{ raw_col('RBP') }}"),
            ('"merClass"', "{{ raw_col('merClass') }}"),
            ('"TDMDScore"', "{{ raw_col('TDMDScore') }}"),
            ('"phyloP"', "{{ raw_col('phyloP') }}"),
            ('"pancancerNum"', "{{ raw_col('pancancerNum') }}"),
            ('"cellline/tissue"', "{{ raw_col('cellline/tissue') }}"),
        ],
    ),
    (
        "dbt/models/marts/dim_lncrna_tissue_profile.sql",
        [("arg_max(tissue, median_tpm)", "{{ arg_max('tissue', 'median_tpm') }}")],
    ),
    (
        "dbt/models/intermediate/int_positive_pairs.sql",
        [
            (
                "string_agg(distinct s.site_type, ',')",
                "{{ string_agg_distinct('s.site_type', ',') }}",
            ),
            (
                "string_agg(distinct cell_context, ',')",
                "{{ string_agg_distinct('cell_context', ',') }}",
            ),
        ],
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    failures: list[str] = []
    for rel, edits in PATCHES:
        path = args.root / rel
        print(f"\n=== {rel}")
        if not path.exists():
            failures.append(f"{rel}: file not found")
            print("  MISSING")
            continue

        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in edits:
            n_old = updated.count(old)
            n_new = updated.count(new)
            if n_old == 0 and n_new >= 1:
                print(f"  already patched: {old}")
                continue
            if n_old != 1:
                failures.append(f"{rel}: found {n_old} occurrences of {old!r}, expected 1")
                print(f"  FAIL {old!r}: {n_old} occurrences, expected 1")
                continue
            updated = updated.replace(old, new)
            print(f"  {old}  ->  {new}")

        if updated == text:
            print("  no change")
        elif args.dry_run:
            print("  (dry run, not written)")
        else:
            path.write_text(updated, encoding="utf-8")
            print("  written")

    if failures:
        print("\n" + "=" * 78)
        for f in failures:
            print(f"  {f}")
        sys.exit("some patches did not apply; nothing was half-written")
    print("\nall patches applied" + (" (dry run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
