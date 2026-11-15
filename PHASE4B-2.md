# Phase 4b, part 2 — the patches

## What the scan actually found

34 hits, of which **25 were noise**: three were my own dispatch macros (which contain the DuckDB
spelling by definition — that's their job), and the `'|'` hits in `int_negative_pairs` were my
regex reading a Jinja macro argument as a quoted identifier. The scanner now strips Jinja
expressions, tags and `{# comments #}` before matching, and skips `macros/portable/`.

Real work, five files:

| File | What | Handled by |
|---|---|---|
| `stg_encori_sites.sql` | 12 mixed-case / punctuated raw columns | `raw_col()` macro, applied by the patcher |
| `dim_lncrna_tissue_profile.sql` | `arg_max` | `arg_max()` macro, applied by the patcher |
| `int_positive_pairs.sql` | 2× `string_agg(distinct …)` | `string_agg_distinct()`, applied by the patcher |
| `int_positive_pairs.sql` L41 | `unnest(string_split(...))` | needs your file — see below |
| `stg_mirna_tissue_atlas.sql` | UNPIVOT + `columns(* exclude …)` | full replacement, included |

## Run

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase4b-2.zip" -DestinationPath . -Force

uv run python scripts\apply_portability_patches.py --dry-run
uv run python scripts\apply_portability_patches.py
uv run python scripts\check_sql_portability.py

cd dbt ; uv run dbt build --profiles-dir . ; cd ..
```

**That last dbt build is the important one** — it runs on DuckDB, and it must still produce
`PASS=82`. The macros are supposed to compile to exactly the SQL that was there before, so if any
number moves, a macro is wrong and we fix it before Snowflake is ever involved.

The patcher verifies each target string occurs exactly once before touching anything; if one
doesn't, it writes nothing and tells you which. Re-running it is safe.

## Two things I still need from you

**`int_positive_pairs.sql`** — the `unnest(string_split(cell_contexts, ','))` on L41 needs a
lateral-flatten rewrite on Snowflake, and that changes the FROM clause, which I can't see. The
macros are ready (`csv_explode_value` + `csv_explode_join`); I need the file to place them.

**Whichever file defines `stable_uniform`** (probably `dbt/macros/stable_uniform.sql`) — see the
decision below.

```powershell
Get-Content dbt\models\intermediate\int_positive_pairs.sql
Get-Content dbt\macros\stable_uniform.sql
```

## The split hash: my recommendation is to leave dev alone

`stable_uniform` is keyed on `gene_id || '|' || mimat_id` and drives the split assignment *and* the
negative sampling. DuckDB's `hash()` and Snowflake's `hash()` return different values for the same
input, so prod would draw a different split.

I said earlier I'd switch to a portable hash. **I now think that's the wrong call**, because
changing `stable_uniform` changes the dev split, which changes the negatives, which invalidates
every benchmark number in §7f–§7k and means retraining everything. A reproducible prod split is
not worth re-running Phase 4 and 5.

So: keep the DuckDB implementation exactly as it is, add a Snowflake branch, and treat the random
draws as **target-local**. `compare_targets.py` now classifies each model as hash-dependent or not,
and only fails on an unexpected difference. `int_lncrna_splits`, `int_negative_pairs`, `fct_pairs`
and `fct_pair_tissue_features` are expected to differ; everything else must match exactly.

What that costs us honestly: prod demonstrates that the models run and the constraints hold on
Snowflake, not that it reproduces the benchmark. **Dev stays authoritative for every reported
number**, and the model card has to say so.

If you'd rather have bit-identical splits, the clean way is to freeze them as an artifact — load
dev's split assignment into Snowflake as a table and have both targets read it — which is also
better engineering than hoping two engines hash alike. That's an extra half-day and three more
model branches. Your call; I'd ship the target-local version and note the limitation.
