# Phase 7b — the demo

| File | Purpose |
|---|---|
| `app/data.py` | bundle loading and every query the app makes — pure, testable, no Streamlit |
| `app/streamlit_app.py` | the UI |
| `tests/test_demo_data.py` | 6 tests on the query layer |
| `scripts/build_demo_bundle.py` | **updated** — now also ships `tissue_map.parquet` |

## Take the bundle update before you build it

The tissue panel needs the GTEx -> organ mapping to put both molecules on one axis, and I had
left `tissue_map` out. If you already ran `build_demo_bundle.py`, just run it again.

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase7b.zip" -DestinationPath . -Force
uv add streamlit
uv run python scripts\build_demo_bundle.py
uv run pytest tests\test_demo_data.py -q
uv run streamlit run app\streamlit_app.py
```

## Five tabs

**Pair lookup** — probability, candidate site count, and the pair's rank in both directions.
**miRNA -> lncRNAs** and **lncRNA -> miRNAs** — ranked tables with CSV download.
**Tissue context** — both molecules' expression across organ systems.
**Benchmark** — the numbers, including the ones that do not flatter the model.

## What the UI refuses to let the user conclude

**Every pair is marked known or not.** A high score on an already-published interaction looks
identical to a discovery unless you say otherwise, so the pair view carries an explicit banner
either way. The "no evidence" wording is deliberate too: most pairs have never been assayed, so
absence of CLIP support is not evidence of absence.

**The tissue tab opens with a warning that it is not a prediction.** Tissue features were tested
as model inputs and carried nothing — every univariate AUROC within 0.013 of chance. Showing a
tissue panel next to a model score invites the reader to assume the model used it. It didn't.
What the panel honestly supports is ruling a context out.

**Each side of the tissue panel is scaled by its own maximum.** The lncRNA is GTEx TPM, the miRNA
is atlas intensity — different assays, different units. Absolute values are not comparable, so
only "where is each near its own peak, and do those overlap" is a legitimate question. The
`both` column is the smaller of the two fractions, and the panel ranks by it rather than by
either side alone — a test covers exactly that, because ranking by either side is the obvious
mistake.

**The benchmark tab leads with the gap, not the headline.** It states that the published method
reached 0.96 AUC under random splits and 0.52 here, that AUROC gains are significant but AUPR
gains are not, and that both the tissue and site-supervision experiments were negative.

## Not yet wired

Per-site attention in the pair view is a stub. It needs the lncRNA sequence and cached features,
which are not in the bundle (they are ~4.6 GB). Options for 7d: ship the attention track for the
precomputed pairs as a seventh parquet, or run it live and accept ~1 s. I would ship the parquet
— it is a few MB if we keep only the top sites per pair.
