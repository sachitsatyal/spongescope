"""Route the last four raw-column references through raw_col().

`start` and `end` are Snowflake reserved words, so the staging models quote them -- but they quote
them in lower case, and the loader stores raw columns upper case, so `"start"` does not bind.
raw_col() emits `"start"` on DuckDB and `"START"` on Snowflake, which satisfies both.

Each replacement is verified to occur exactly once before anything is written, and re-running is
safe.

Usage:
    uv run python scripts/apply_reserved_word_patches.py --dry-run
    uv run python scripts/apply_reserved_word_patches.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PATCHES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "dbt/models/staging/stg_encori_sites.sql",
        [('"start"', "{{ raw_col('start') }}"), ('"end"', "{{ raw_col('end') }}")],
    ),
    (
        "dbt/models/staging/stg_gencode_exons.sql",
        [('"start"', "{{ raw_col('start') }}"), ('"end"', "{{ raw_col('end') }}")],
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
            n_old, n_new = updated.count(old), updated.count(new)
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
