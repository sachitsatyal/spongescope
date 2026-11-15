"""Find every construct in the dbt models that will not run on Snowflake.

Rather than patching from memory, this reports file and line for each one so the fix is exact.
Also prints the prod profile block and which SNOWFLAKE_* variables are set, since a missing
credential looks like a SQL error from the outside.

Usage:
    uv run python scripts/check_sql_portability.py
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

# Snowflake reserved words that plausibly appear as raw column names. A bare reserved word is a
# syntax error in DDL and in queries, so any of these referring to a raw column must go through
# raw_col(), which quotes it.
SNOWFLAKE_RESERVED = [
    "start",
    "end",
    "order",
    "group",
    "table",
    "column",
    "view",
    "schema",
    "values",
    "row",
    "rows",
    "select",
    "from",
    "where",
    "check",
    "constraint",
    "current",
    "increment",
    "sample",
    "set",
    "to",
    "of",
    "is",
    "in",
    "on",
    "or",
    "and",
    "not",
    "null",
    "true",
    "false",
]

# Each rule: (label, regex, what to do about it)
RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "UNPIVOT",
        re.compile(r"\bunpivot\b", re.IGNORECASE),
        "Snowflake UNPIVOT needs an explicit column list -> reshape in the loader instead",
    ),
    (
        "columns(* exclude ...)",
        re.compile(r"columns\s*\(\s*\*\s*exclude", re.IGNORECASE),
        "DuckDB-only column expression",
    ),
    (
        "* EXCLUDE / * REPLACE",
        re.compile(r"\*\s*(exclude|replace)\s*\(", re.IGNORECASE),
        "DuckDB star modifier; list columns explicitly",
    ),
    (
        "string_agg",
        re.compile(r"\bstring_agg\s*\(", re.IGNORECASE),
        "use {{ string_agg_distinct(col, delim) }} (dispatches to listagg)",
    ),
    (
        "string_split / str_split",
        re.compile(r"\b(string_split|str_split|string_to_array)\s*\(", re.IGNORECASE),
        "Snowflake: split() returns an array; needs lateral flatten, not a select-position call",
    ),
    (
        "unnest",
        re.compile(r"\bunnest\s*\(", re.IGNORECASE),
        (
            "no select-position unnest on Snowflake -> restructure to aggregate from base "
            "rows, or use lateral flatten"
        ),
    ),
    (
        "arg_max / arg_min",
        re.compile(r"\barg_(max|min)\s*\(", re.IGNORECASE),
        "use {{ arg_max(value_col, order_col) }} (dispatches to max_by)",
    ),
    (
        "GROUP BY ALL",
        re.compile(r"\bgroup\s+by\s+all\b", re.IGNORECASE),
        "Snowflake supports GROUP BY ALL since 2023, but list the columns to be safe",
    ),
    (
        "list / array aggregate",
        re.compile(r"\b(list|array_agg)\s*\(\s*distinct", re.IGNORECASE),
        "check array semantics differ between engines",
    ),
    (
        "quoted mixed-case identifier",
        re.compile(r'"[A-Za-z_]*[A-Z][A-Za-z_]*"'),
        (
            "Snowflake stores unquoted names uppercase; a quoted mixed-case name will not "
            "bind unless the loader preserved that exact case"
        ),
    ),
    (
        "quoted identifier with punctuation",
        re.compile(r'"[^"]*[^A-Za-z0-9_"][^"]*"'),
        "loader normalizes these to snake_case; the model must use the normalized name",
    ),
    (
        "regexp_matches",
        re.compile(r"\bregexp_matches\s*\(", re.IGNORECASE),
        "Snowflake: regexp_like",
    ),
    (
        "epoch_ms / strftime",
        re.compile(r"\b(epoch_ms|strftime)\s*\(", re.IGNORECASE),
        "different date functions on Snowflake",
    ),
]

SKIP_DIRS = {"target", "logs", "dbt_packages", ".venv", "__pycache__"}

# Only staging models read raw tables, so only there does a bare or lowercase-quoted identifier
# refer to a column the loader renamed. Everywhere else the columns are dbt's own, and dbt
# handles their quoting.
RAW_READING_DIR = ("models", "staging")

# Rules that apply only to staging. Checked separately from RULES, which apply everywhere.
STAGING_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "lowercase-quoted raw column",
        re.compile(r'"[a-z][a-z0-9_]*"'),
        (
            "the loader stores raw columns UPPER CASE, so a lowercase-quoted name will not "
            "bind -> wrap in {{ raw_col('name') }}"
        ),
    ),
    (
        "bare reserved word as a column",
        re.compile(
            r"(?:^|,)\s*(" + "|".join(SNOWFLAKE_RESERVED) + r")\s*(?:,|\s+as\s)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "Snowflake reserved word read as a raw column -> wrap in {{ raw_col('name') }}",
    ),
]
# Our own dispatch macros contain the DuckDB spelling by definition -- that is their job.
SKIP_PATHS = {("macros", "portable")}

# A model that handles both warehouses in explicit branches legitimately contains the DuckDB
# spelling. Put this marker in such a file and the scanner reports it as handled instead of
# flagging every line of the DuckDB branch.
SUPPRESS_MARKER = "portable-ok: adapter-dispatched"

JINJA_BLOCK = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)


def strip_noise(text: str) -> str:
    """Blank out Jinja comments, expressions and tags, keeping line numbers intact.

    Without this, a macro argument like "g.gene_id || '|' || ms.mimat_id" reads as a quoted
    identifier, and prose inside a {# comment #} reads as SQL.
    """

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return JINJA_BLOCK.sub(blank, JINJA_COMMENT.sub(blank, text))


def scan(root: Path) -> tuple[list[tuple[Path, int, str, str, str]], list[Path]]:
    hits: list[tuple[Path, int, str, str, str]] = []
    suppressed: list[Path] = []
    for path in sorted(root.rglob("*.sql")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if any(all(p in path.parts for p in combo) for combo in SKIP_PATHS):
            continue
        raw = path.read_text(encoding="utf-8")
        if SUPPRESS_MARKER in raw:
            suppressed.append(path)
            continue
        cleaned = strip_noise(raw)
        for lineno, line in enumerate(cleaned.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            rules = RULES
            if all(part in path.parts for part in RAW_READING_DIR):
                rules = RULES + STAGING_RULES
            for label, pattern, advice in rules:
                if pattern.search(line):
                    hits.append((path, lineno, label, stripped, advice))
    return hits, suppressed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbt-dir", type=Path, default=Path("dbt"))
    args = ap.parse_args()

    hits, suppressed = scan(args.dbt_dir)
    if not hits:
        print("No DuckDB-only constructs found.")
    else:
        print(f"{len(hits)} construct(s) to make portable:\n")
        current: Path | None = None
        for path, lineno, label, line, advice in hits:
            if path != current:
                print(f"\n=== {path.as_posix()}")
                current = path
            text = line if len(line) <= 150 else line[:147] + "..."
            print(f"  L{lineno:<4} [{label}]")
            print(f"        {text}")
            print(f"        -> {advice}")

    if suppressed:
        print("\nHandled by explicit adapter branches (marker present, not scanned):")
        for p in suppressed:
            print(f"  {p.as_posix()}")

    print("\n" + "=" * 78)
    print("Files containing a hit (paste these to me so the patch is exact):")
    for p in sorted({h[0] for h in hits}):
        print(f"  {p.as_posix()}")

    print("\n" + "=" * 78)
    print("SNOWFLAKE_* environment variables:")
    found = False
    for key in sorted(os.environ):
        if key.startswith("SNOWFLAKE"):
            found = True
            value = os.environ[key]
            shown = "<set>" if "PASS" in key or "KEY" in key or "TOKEN" in key else value
            print(f"  {key} = {shown}")
    if not found:
        print("  (none set)")

    profiles = args.dbt_dir / "profiles.yml"
    if profiles.exists():
        print("\n" + "=" * 78)
        print(f"{profiles.as_posix()} (so the loader uses the same names):")
        for line in profiles.read_text(encoding="utf-8").splitlines():
            print(f"  {line}")


if __name__ == "__main__":
    main()
