---
license: mit
tags:
  - biology
  - rna
  - lncrna
  - mirna
  - interaction-prediction
pipeline_tag: tabular-classification
---

# SpongeScope v1

Predicts whether a long non-coding RNA and a microRNA interact. 697,857 parameters; runs on CPU
in about 5 ms per pair once the lncRNA's embedding is cached.

## The number that matters

Evaluated **cold-start**: test lncRNAs share no MMseqs2 sequence cluster (80% identity) with any
training lncRNA, and 10% of miRNA seed families are held out entirely.

| group | AUROC | AUPR | positive rate | ECE |
|---|---|---|---|---|
| cold lncRNA | 0.841 | 0.303 | 0.096 | 0.009 |
| seed-controlled | 0.753 | 0.312 | 0.163 | 0.016 |
| cold lncRNA + miRNA | 0.853 | 0.297 | 0.087 | 0.021 |

precision@10 per lncRNA is **0.274** against a 0.096 base rate — test ten candidates, get about
2.7 real ones instead of one.

## What this model does not establish

**A precision improvement is not statistically established.** Against a gradient-boosted baseline
on the same features, AUROC gains are significant on 3 of 6 paired comparisons and positive on
all 6; **no AUPR gain is significant**. With 149 test lncRNAs the AUPR confidence interval is
±0.03-0.05, so differences below ~0.05 cannot be resolved on this benchmark at all. The honest
claim is that it ranks better, not that it is more precise.

**Most of the signal is in the seed-site scanner, not the network.** A gradient-boosted model
over the same candidate sites reaches 0.824 AUROC. The neural model's contribution is the
cross-attention between site context and the miRNA, worth about 0.025 AUPR; removing it drops
performance to baseline.

## Two negative results, reported rather than buried

**Tissue context adds nothing.** Eleven expression features (co-expression across organs,
co-occurrence, breadth, abundance) were built and tested. Every univariate AUROC fell between
0.487 and 0.508 — chance. A gradient-boosted model given the features directly showed no
significant gain. Two structural reasons: the labels come from CLIP experiments in *cell lines*,
so organ-level co-expression cannot explain detection; and the negative sampling already draws
from real, abundant miRNAs, so co-expression is equally high on both sides by construction.

**Site-level supervision made it worse.** Labelling each candidate site by overlap with a real
CLIP peak (122,141 site labels) and adding an auxiliary head: all six paired comparisons
negative, one significantly so. The auxiliary loss was learned — site loss fell to 0.150 — so the
model can locate sites; knowing which one is real simply does not improve the pair call. The
scanner already contains the true site for 94.9% of positive pairs, so localization was never the
bottleneck.

## Training data and its biases

ENCORI CLIP-supported lncRNA-miRNA pairs (15,962 positives over 1,313 lncRNAs and 638 miRNAs),
GENCODE 50 transcripts, miRBase mature sequences. Negatives at ~8:1, **half seed-matched**: the
lncRNA contains a 7mer site for the miRNA but has no CLIP support. Without those hard negatives,
counting seed matches alone scores 0.88 AUROC, because CLIP peaks carry seed matches by
construction — a circularity that inflates every published number built on this kind of label.

A negative label means "not observed", not "does not interact". Coverage is biased toward
well-studied miRNAs and toward whatever cell lines were assayed.

## Intended use

Ranking candidates for experimental follow-up. Not a substitute for experimental validation, and
not calibrated for clinical or diagnostic use of any kind.

## Reproducing

Benchmark, splits and both negative results are reproducible from the repository: cluster-based
splits are deterministic given the seed, and every metric is computed by one shared evaluation
module with lncRNA-level bootstrap confidence intervals.
