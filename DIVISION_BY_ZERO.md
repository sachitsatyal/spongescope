# The one real portability bug: division by zero

`dim_lncrna_tissue_profile` failed on Snowflake with `100051 (22012): Division by zero`.

## Why the existing guard didn't work

```sql
case
    when s.max_log1p_tpm = 0 then null
    else sum(1 - e.log1p_tpm / s.max_log1p_tpm) / (s.n_tissues - 1)
end as tau
```

The division sits **inside `sum()`**. Aggregates are computed over the whole group before the
CASE picks a branch, so the per-row division runs for every row whatever the guard says. The CASE
only chooses which already-computed value to return.

DuckDB survives because `x / 0` yields NULL there. **Snowflake raises.** That difference is the
actual portability issue — the SQL was always relying on DuckDB's lenient arithmetic.

There was a second, unguarded one too: `/ (s.n_tissues - 1)` divides by zero for any gene with
exactly one tissue row.

## The fix

```sql
sum(1 - e.log1p_tpm / nullif(s.max_log1p_tpm, 0))
    / nullif(s.n_tissues - 1, 0)                       as tau
```

`nullif()` puts the guard where the division happens. Identical results on both engines: NULL
when a gene has no expression anywhere (max = 0 — the 179 genes expressed in no tissue) or has
only one tissue row.

The CASE is gone because it was never doing the job it looked like it was doing.

## Also in this zip: a stronger equivalence check

`compare_targets.py` now hashes the **sorted set of keys** per model, so "same row count" becomes
"same rows". Row counts and means can agree while the rows differ — two split assignments with
the same 80/10/10 counts, for instance. Models without a key column are now labelled
`[no key column: row counts and means only, NOT row-level equivalence]` rather than a bare
"match".

`dim_mirna` is reclassified as **hash-dependent**: it carries `is_holdout`, which comes from
`int_mirna_holdout` and therefore from `stable_uniform`. That was my misclassification, and it is
why `mean_is_holdout` showed as an unexpected difference.

## Run

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase4b-9.zip" -DestinationPath . -Force

cd dbt
uv run dbt build --profiles-dir .
uv run dbt build --target prod --profiles-dir .
cd ..
uv run python scripts\compare_targets.py
```

Dev first: `nullif()` must not change any dev number, so `PASS=82` is the check before spending
anything on Snowflake. Then prod should also be `PASS=82`.

Expect `compare_targets.py` to now report the hash-dependent four (`dim_mirna`,
`int_lncrna_splits`, `int_negative_pairs`, `fct_pairs`, plus `fct_pair_tissue_features`) as
expected differences, and everything else matching — this time including key checksums, which is
a real claim rather than an aggregate one.
