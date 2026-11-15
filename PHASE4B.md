# Phase 4b — Snowflake as the prod warehouse

Goal: the **same dbt models** run on DuckDB (`dev`, free, local) and Snowflake (`prod`), and
`dbt build --target prod` passes the same 82 checks with the same numbers.

## What's in this zip

| File | Purpose |
|---|---|
| `scripts/check_sql_portability.py` | **run this first** — finds every DuckDB-only construct in your SQL, with file and line |
| `src/spongescope/data/load_snowflake.py` | DuckDB `raw.*` → Snowflake `RAW` schema; handles identifier case and the wide atlas |
| `dbt/macros/portable/string_agg_distinct.sql` | `string_agg(distinct …)` → `listagg(distinct …)` on Snowflake |
| `dbt/macros/portable/arg_max.sql` | `arg_max(v, o)` → `max_by(v, o)` on Snowflake |
| `dbt/macros/portable/atlas_source.sql` | `atlas_is_prereshaped()` — the one place the two targets genuinely diverge |
| `scripts/compare_targets.py` | row counts, key cardinality, label balance and per-column means, dev vs prod |

Model patches are **not** in this zip on purpose. Rather than rewrite SQL I can't see, the scanner
reports exactly which files and lines need changing; paste its output and the patch will be exact.

## Step 1 — scan before signing up (no account needed, ~2 seconds)

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase4b.zip" -DestinationPath . -Force
uv run python scripts\check_sql_portability.py
```

This also prints your `dbt/profiles.yml` prod block and which `SNOWFLAKE_*` variables are set, so
the loader can be aligned to the names already in the profile.

Doing this first means the 30-day trial clock starts only once the SQL work is scoped.

## Step 2 — create the trial account

<https://signup.snowflake.com> — no card required. Two choices matter:

- **Cloud provider: AWS, region us-east-1.** Matches §4's note so any later S3 staging is in the
  same region (cross-region egress is the one way a free trial can burn balance unexpectedly).
- **Edition: Standard.** Enterprise spends trial credits faster for features we don't use.

The trial ends after 30 days *or* when the free balance runs out, whichever comes first, and the
account is then suspended — so treat anything in Snowflake as reproducible from DuckDB, never as
the only copy.

## Step 3 — credentials as environment variables

Never commit these. For the current session only:

```powershell
$env:SNOWFLAKE_ACCOUNT  = "abcd-xy12345"   # the account identifier, not the full URL
$env:SNOWFLAKE_USER     = "<username>"
$env:SNOWFLAKE_PASSWORD = "<password>"
$env:SNOWFLAKE_ROLE     = "ACCOUNTADMIN"
$env:SNOWFLAKE_WAREHOUSE = "SPONGESCOPE_WH"
$env:SNOWFLAKE_DATABASE  = "SPONGESCOPE"
```

To persist them for your user (survives reboots, still not in the repo):

```powershell
[Environment]::SetEnvironmentVariable("SNOWFLAKE_ACCOUNT", "abcd-xy12345", "User")
```

The account identifier is in the Snowflake UI under your account menu, or it's the first part of
your login URL (`abcd-xy12345.snowflakecomputing.com`).

## Step 4 — load the raw data

```powershell
uv run python -m spongescope.data.load_snowflake --dry-run
uv run python -m spongescope.data.load_snowflake
```

The dry run needs no credentials: it lists each raw table, its size, the target table name, and
every column it would rename. **Read the rename list** — any model that referenced an original
name (`"miRNAid"`, `"cellline/tissue"`) has to use the normalized one.

The loader creates the warehouse (XSMALL, 60-second auto-suspend, starts suspended), the database
and the `RAW` schema if they don't exist, replaces each table, then reads the row counts back from
Snowflake and prints them next to the source counts.

Biggest table is `gtex_median_tpm` at ~4M rows; expect a few minutes.

## Step 5 — build and compare

```powershell
cd dbt ; uv run dbt build --target prod --profiles-dir . ; cd ..
uv run python scripts\compare_targets.py
```

Tests passing proves the SQL *runs*. It does not prove the two warehouses produced the same
numbers — a different split assignment, a row lost to an identifier mismatch, or a float that
rounds differently would all pass. `compare_targets.py` is what checks equivalence, and it exits
non-zero if anything differs.

## Three things I expect to be awkward

**The atlas unpivot.** Snowflake's `UNPIVOT` requires an explicit column list and the atlas is
2,660 columns wide. Generating that list would break on every atlas re-release, so the loader
reshapes it in pandas and writes `mirna_tissue_atlas_long`. On Snowflake,
`stg_mirna_tissue_atlas` becomes a thin passthrough. This is a real divergence, not a syntax
swap: the reshaping logic is then covered by the loader rather than by a dbt test, so
`compare_targets.py` on `fct_mirna_tissue_expression` is what proves the two paths agree.

**`unnest(string_split(...))`.** Snowflake has no select-position unnest — `split()` returns an
array and you need `lateral flatten`. A macro can't paper over that difference in shape, so the
better fix is usually to restructure the model to aggregate from the base rows instead of
splitting a string it just built. Which applies depends on what the scanner finds.

**The deterministic hash.** `stable_uniform` already dispatches on adapter, but Snowflake's
`hash()` and DuckDB's `hash()` return different values for the same input. That means the
**train/val/test split and the negative sampling will differ between targets** unless the hash is
made identical. This matters more than it looks: a different split on prod would make the two
warehouses incomparable and would invalidate `compare_targets.py` on `fct_pairs`. Options are to
use a portable hash (`md5` of the key, cast to a number — same result everywhere), or to accept
prod as a pipeline demonstration and keep dev authoritative for the benchmark. I'd pick the
portable hash, and the scanner output will show where `stable_uniform` is used.
