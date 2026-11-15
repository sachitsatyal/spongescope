# Uppercase quoted identifiers, and why

## What broke

`create table ... (start NUMBER(38,0), ...)` — `start` is a **Snowflake reserved word**, so a bare
`start` is a syntax error in DDL, not just in queries. ENCORI has `start` and `end` coordinate
columns. That was the `unexpected 'start'`; the `'0'` and `','` errors after it were the parser
losing its place on `NUMBER(38,0)`.

The seven dbt errors and the eleven comparison errors were all downstream of that: no raw tables
loaded, so nothing to build and nothing to compare.

## The fix: uppercase AND quoted

The loader now normalizes to **upper case** and writes with `quote_identifiers=True`.

Those two choices only work together:

| strategy | reserved words | binds to unquoted `select gene_id` |
|---|---|---|
| lowercase, unquoted | **breaks** | yes |
| lowercase, quoted | fine | **no** — stored as `gene_id`, lookup is `GENE_ID` |
| **uppercase, quoted** | fine | yes |

Upper case is what Snowflake stores for an unquoted name anyway, so quoting costs nothing and
sidesteps the whole reserved-word class of problem. `raw_col()` now emits `"MIRNAID"` on
Snowflake rather than bare `mirnaid`, to match.

## One more patch needed — and I need two files

Any model that selects a reserved word *from a raw table* still has to go through `raw_col()`,
because a bare `start` fails in a query too. The scanner has a new rule for this, so run it first:

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase4b-7.zip" -DestinationPath . -Force
uv run pytest tests\test_load_snowflake.py -q
uv run python scripts\check_sql_portability.py
```

Then paste the scanner output **and** these two files:

```powershell
Get-Content dbt\models\staging\stg_encori_sites.sql
Get-Content dbt\models\staging\stg_gencode_exons.sql
```

Those are the two that read coordinate columns, so they are where `start`/`end` will be. Once
they're patched the load and build should both go through.

You can run the loader now regardless — it no longer depends on those models:

```powershell
uv run python -m spongescope.data.load_snowflake
```

Expect seven tables, renames reported per table (now upper case), and the atlas reshaping to
~1.7M long rows with miRNA names kept verbatim.
