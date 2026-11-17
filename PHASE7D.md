# README and CI

## README.md

Written for someone who lands on the repo cold. It leads with the thing that makes the project
worth reading — a published method reports AUC 0.96, the same method under leakage-free
evaluation reaches 0.52 — and then explains why the benchmark is the contribution: cold-start
clustering, hard negatives that remove the seed-matching circularity, paired significance
testing, and the stated resolution limit.

It states what is **not** established (no significant AUPR gain), reports both negative results,
and names the dual-warehouse `least()` bug as a concrete argument for running the same models on
two engines.

Replace it as the repo root README:

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-readme-ci.zip" -DestinationPath . -Force
```

Read it before pushing — it makes claims in your name, and you should agree with all of them.

## .github/workflows/ci.yml

Three jobs, each chosen so it can actually pass without data in the runner:

**lint** — `ruff check` and `ruff format --check`, installing only ruff. Pulling in torch
(~800 MB, several minutes) to check formatting would make the fast signal slow enough that nobody
waits for it.

**dbt parse** — compiles every model and macro without connecting to a warehouse. That catches
Jinja errors, bad `ref()`s and malformed YAML, which are exactly the failures that have bitten
this project: the `: ` in a description that broke YAML parsing, the I001 import ordering, the
`ISC004` strings. No data needed.

**pytest (data-independent)** — `test_demo_data.py` and `test_load_snowflake.py` only. The rest
of the suite needs the 4.6 GB feature cache or a trained checkpoint, neither of which belongs in
CI. The package installs with `--no-deps` so `import spongescope` resolves without the training
stack.

`concurrency` cancels superseded runs on the same branch — on a free plan the minutes are the
scarce resource.

**What CI deliberately does not do:** it does not train, does not build the warehouse, and does
not touch Snowflake. A CI that needs 4.6 GB of cached embeddings is a CI that is always red,
and a red CI nobody can fix is worse than none.

## Next

Nextflow (`main.nf` with test/kaggle profiles) and DagsHub (DVC remote + hosted MLflow). Those
are the last two items in Phase 7.
