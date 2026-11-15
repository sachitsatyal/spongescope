# Phase 6a — tissue context features

## What this adds

| File | Purpose |
|---|---|
| `dbt/seeds/tissue_map.csv` | 68 GTEx tissues -> 28 atlas organ systems, curated by hand |
| `dbt/seeds/_seeds.yml` | seed docs + uniqueness test on `gtex_tissue` |
| `dbt/models/intermediate/int_mirna_name_map.sql` | miRBase name -> atlas column name (exact, then safe arm-stripping) |
| `dbt/models/marts/fct_mirna_tissue_expression.sql` | **replaces** the existing file — now joins through the name map |
| `dbt/models/marts/fct_pair_tissue_features.sql` | 11 expression-context features per pair |
| `dbt/models/marts/_marts_tissue_features.yml` | tests on both new models |
| `dbt/tests/assert_tissue_features_cover_all_pairs.sql` | every pair gets a row; `coexpr` in [-1, 1] |
| `scripts/report_name_map.py` | how many miRNAs reached the atlas, and which didn't |
| `scripts/check_tissue_signal.py` | **the decision point** — GBM with vs without tissue features |

## Why organ-level mapping

GTEx has 68 tissue names, the atlas has 137. Pairing them individually is 68 judgment calls with
no ground truth. But GTEx names carry an organ prefix (`Brain_Cortex`, `Artery_Aorta`) and the
atlas already groups its tissues under `organ_system`, so matching at organ level needs ~28
decisions and each one is defensible. 66 of 68 GTEx tissues map; the two left blank are
`Cells_Cultured_fibroblasts` and `Cells_EBV-transformed_lymphocytes`, which are cell cultures,
not tissues. Judgment calls are recorded in the `note` column — `Fallopian_Tube -> ovary` and
`Pituitary -> brain` (the atlas files `pituitary_gland` under `brain`) are the two to argue with.

## Why arm-stripping is conditional

529 of our 638 miRNAs match the atlas by name exactly. Most of the rest are miRNAs with one
annotated arm, where the atlas uses the older un-suffixed name (`hsa-miR-107` for our
`hsa-miR-107-3p`). We strip the arm **only** when the atlas has the stem and neither `-5p` nor
`-3p`; if both arms are present the stem is ambiguous, and -5p and -3p are different molecules
with different targets, so a wrong merge would be worse than a missing row.

## Run it

Unzip so that `dbt/` and `scripts/` land **on top of the existing folders** in the project root.

dbt must run from inside `dbt/`: the DuckDB path in `profiles.yml` is relative to the current
directory, not to `--project-dir`, so running it from the project root points at the wrong file.

```powershell
cd $HOME\projects\spongescope\dbt
uv run dbt build --profiles-dir .
cd ..
uv run python scripts\report_name_map.py
uv run python scripts\check_tissue_signal.py
```

`dbt build` runs seeds first, so there is no separate `dbt seed` step. Expect **24 models** in the
parse line (was 21); if it still says 21, the zip didn't land in the right place.

## How to read the verdict

`check_tissue_signal.py` trains the same gradient-boosted model twice — site features alone,
then site + tissue — and bootstraps the **difference** in AUPR at lncRNA level. That is the same
paired test we used for v2, and the same reason: the benchmark's CI half-width is +/-0.03-0.05
AUPR, so separate overlapping CIs cannot resolve a real gain.

The last line prints the decision. If `test_cold_lncrna` is not significant, tissue features do
not go into the neural model — a GBM given the features directly is a generous upper bound on
what the neural path would extract from them, so a null here closes the question cheaply.

Watch the coverage table too. Any tissue feature below ~70% non-null is mostly measuring
"is this miRNA in the atlas", not biology, and `mirna_atlas_known` is in the feature set
precisely so the model can condition on missingness instead of treating NaN as zero.
