# SpongeScope

Predicting lncRNA–miRNA interactions, evaluated so the number means something.

**[Live demo](https://huggingface.co/spaces/sawcheet/spongescope)** ·
**[Model](https://huggingface.co/sawcheet/spongescope)**

---

## The short version

A published method for this task reports **AUC ≈ 0.96**. Re-implemented faithfully and evaluated
without leakage, it reaches **0.52** — chance. The gap is not the architecture; it is that the
original splits pairs at random, so the same lncRNA appears in training and test.

SpongeScope is built against that honest benchmark: cold-start splits, hard negatives that remove
the seed-matching shortcut, and paired significance testing. It reaches **AUROC 0.841 / AUPR
0.303** on held-out lncRNAs, is calibrated (ECE 0.009), and runs on CPU in ~5 ms per pair.

It also contains two negative results that are reported rather than buried, because they are more
informative than another incremental AUROC.

## Why the benchmark is the contribution

**Cold-start splits.** lncRNAs are clustered with MMseqs2 at 80% identity and whole clusters go
to one split, so no test lncRNA has a near-duplicate in training. 10% of miRNA seed families are
held out entirely, giving a second evaluation group where both molecules are unseen.

**Hard negatives.** CLIP-derived positives carry seed matches *by construction* — the peak is
called partly from the seed. So counting seed matches alone scores 0.88 AUROC, and any model
trained against random negatives inherits that circularity. Half the negatives here are
**seed-matched**: the lncRNA contains a 7mer site for the miRNA but has no CLIP support. That
narrows the seed-counting advantage from 64 points to 43 and creates a `test_seed_controlled`
group that measures what a model adds *beyond* seed matching.

**Significance, not point estimates.** Differences are tested with a paired lncRNA-level
bootstrap — the same resampled lncRNAs for both models — rather than by eyeballing overlapping
confidence intervals.

**The resolution limit is stated.** With 149 test lncRNAs the AUPR confidence interval is
±0.03–0.05. Differences below ~0.05 AUPR cannot be resolved on this benchmark, so chasing +0.02
is not science. That bound shaped every decision after Phase 5.

## Results

| group | AUROC | AUPR | positive rate | ECE |
|---|---|---|---|---|
| cold lncRNA | 0.841 | 0.303 | 0.096 | 0.009 |
| seed-controlled | 0.753 | 0.312 | 0.163 | 0.016 |
| cold lncRNA + miRNA | 0.853 | 0.297 | 0.087 | 0.021 |

precision@10 per lncRNA is **0.274** against a 0.096 base rate — test ten candidates, get ~2.7
real ones instead of one.

**What is not established:** no AUPR gain over a gradient-boosted baseline on the same features
is statistically significant. AUROC gains are significant on 3 of 6 paired comparisons and
positive on all 6. The honest claim is that it *ranks* better, not that it is more precise.

## Two negative results

**Tissue context adds nothing.** Eleven expression features — organ-level co-expression,
co-occurrence, breadth, abundance — all landed between 0.487 and 0.508 univariate AUROC. Chance.
Two structural reasons: the labels come from CLIP experiments in *cell lines*, so organ-level
co-expression cannot explain detection; and the negatives are drawn from real, abundant miRNAs,
so co-expression is equally high on both sides by construction. The benchmark cannot reward
tissue context at the pair level, which is a property of the design, not a failure of the
features.

**Site-level supervision made it worse.** Labelling each candidate site by overlap with a real
CLIP peak (122,141 site labels) and adding an auxiliary head: all six paired comparisons
negative, one significantly so. The auxiliary loss *was* learned — site loss fell to 0.150 — so
the model can locate sites. Knowing which site is real simply does not improve the pair call.
The scanner already contains the true site for 94.9% of positive pairs, so localization was
never the bottleneck.

## How it works

1. **Scan** the lncRNA for candidate seed sites against the miRNA (8mer, 7mer-m8, 7mer-A1, 6mer,
   offset-6mer, and one-mismatch/G:U), keeping up to 16 ranked by type then accessibility.
2. **Encode** each site: an 81-nt window of frozen RNA-FM embeddings plus RNAplfold
   accessibility, cross-attending the miRNA's own token embeddings.
3. **Pool** sites with attention-based multiple-instance learning, so the model decides which
   sites matter and the weights double as a per-site explanation.
4. **Calibrate** with temperature scaling fitted on validation logits.

Ablations (3 seeds): cross-attention is worth ~0.025 AUPR and is what lifts the model above the
scanner+GBM baseline; RNA-FM is worth ~0.014; accessibility is worth nothing measurable.

## Quickstart

```bash
uv sync
uv run python -m spongescope.data.download
uv run python -m spongescope.data.load_raw
cd dbt && uv run dbt build --profiles-dir . && cd ..
uv run python -m spongescope.features.rnafm_embed
uv run python -m spongescope.features.accessibility
uv run python -m spongescope.features.sites
uv run python -m spongescope.train_site
```

The lncRNA clustering step runs on Colab (`notebooks/colab_mmseqs_cluster.ipynb`) because MMseqs2
has no current Windows build; its output is a TSV tracked by DVC.

## Stack

| Layer | Choice |
|---|---|
| Warehouse | DuckDB (dev) and Snowflake (prod), same dbt models |
| Transformations | dbt — 23 models, 58 tests, both targets green |
| Model | PyTorch + Lightning, Hydra configs, MLflow tracking |
| Data versioning | DVC |
| Serving | safetensors export, `spongescope.inference`, Streamlit on HF Spaces |
| Quality | pytest, ruff, pre-commit |

**On the dual warehouse:** running the same models on two engines caught a real bug neither
engine's tests would have found. `least()` ignores NULL arguments on DuckDB and propagates them
on Snowflake, so a lncRNA with no expression anywhere was silently scored with its partner's
abundance for 1,874 pairs. Each engine was internally consistent; only the comparison exposed it.

**Honest limitation:** the random draws (split assignment, negative sampling) depend on a hash
that differs between the two engines, so they are target-local. Dev is authoritative for every
reported number; prod demonstrates portability, not reproduction of the benchmark.

## Repository layout

```
dbt/            23 models: staging -> intermediate -> marts, dual-target
src/spongescope/
  data/         download, raw load, Snowflake loader
  features/     RNA-FM embeddings, accessibility, site scanner, site tables
  models/       SiteMIL and the re-implemented baseline
  baselines/    classic and site-level gradient-boosted baselines
  evaluation/   shared metrics, calibration, paired bootstrap
  inference.py  the serving path, shared with training to prevent drift
app/            the demo
scripts/        reporting, export, benchmarking, deployment
```

## Data

GENCODE 50 lncRNA transcripts · miRBase mature miRNAs · ENCORI CLIP-supported interactions ·
GTEx v10 median TPM · miRNATissueAtlas 2025.

A negative label means "not observed", not "does not interact". Coverage is biased toward
well-studied miRNAs and whichever cell lines were assayed.

## License

MIT.
