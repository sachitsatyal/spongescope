---
title: SpongeScope
emoji: 🧬
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 8501
pinned: false
license: mit
short_description: Leakage-free lncRNA-miRNA interaction prediction
---

# SpongeScope

Predicts whether a long non-coding RNA and a microRNA interact, evaluated so that the number
means something: test lncRNAs share no sequence cluster with training, and 10% of miRNA seed
families are held out entirely.

**What the demo shows.** Browse ~838k precomputed pairs in either direction, see whether a pair
already has CLIP evidence, and look at where both molecules are expressed.

**What the numbers mean.** On held-out lncRNAs: AUROC 0.841, AUPR 0.303 against a 0.096 positive
rate, ECE 0.009. Testing the top 10 ranked candidates for a lncRNA returns about 2.7 real
interactions instead of ~1 at random.

**What it does not do.** It does not establish a precision improvement over a well-tuned
gradient-boosted baseline — AUROC gains are statistically significant, AUPR gains are not, and
with 149 test lncRNAs the AUPR confidence interval is ±0.03-0.05. It has no notion of tissue:
expression features were tested and carried no signal. "No evidence" for a pair almost always
means nobody has assayed it.

Model: [sawcheet/spongescope](https://huggingface.co/sawcheet/spongescope) ·
Code: [github.com/sachitsatyal/spongescope](https://github.com/sachitsatyal/spongescope)
