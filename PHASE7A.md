# Phase 7a — precomputed scores and the demo bundle

The demo cannot compute on demand. Free Hugging Face Spaces is CPU-only; a cached pair takes
~5 ms, which is fine for one lookup and useless for "rank 638 miRNAs against this lncRNA" on
every page load. So the full grid is scored once and the demo reads parquet files.

| File | Purpose |
|---|---|
| `scripts/precompute_scores.py` | scores 1,313 lncRNAs x 638 miRNAs (~838k pairs) into resumable shards |
| `scripts/build_demo_bundle.py` | assembles the shards plus identity, tissue and known-pair tables into `data/demo/` |
| `tests/test_demo_bundle.py` | the ranking the demo browses by |

## Run

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase7a.zip" -DestinationPath . -Force

uv run python scripts\precompute_scores.py --check
uv run python scripts\precompute_scores.py --genes 5
```

`--check` reads nothing heavy: it reports how many lncRNAs have embeddings and accessibility on
disk and stops. `--genes 5` scores ~3,200 pairs, which tells you in under a minute whether the
full run will work and what rate to expect.

Then the real run. **Expect roughly an hour**, single-threaded on CPU:

```powershell
uv run python scripts\precompute_scores.py
uv run python scripts\build_demo_bundle.py
uv run pytest tests\test_demo_bundle.py -q
```

It writes one shard per 25 genes and skips shards that already exist, so closing the terminal
costs you at most one shard. Progress prints a live pairs/sec and an estimate of time remaining.

## Two decisions worth knowing

**Ranks are computed once, at bundle time, not in the app.** The demo's two main views are "top
miRNAs for this lncRNA" and the reverse; ranking 838k rows once here means the app never sorts.
The tie-break is `method="first"` rather than `"min"` — with `"min"`, four tied scores all get
rank 1 and a "top 10" returns 11 rows. That is the same tie-break bug that produced the fake
`length_only` p@1 = 0.66 in Phase 5b, so it is tested.

**`known_pairs.parquet` ships deliberately.** Without it the demo would present a high score for
an already-published interaction as if it were a discovery. With it, the UI can mark a pair as
having CLIP evidence, and say which split it came from. That distinction is most of the
difference between a screening tool and a demo that overstates itself.

## Next

7b is the Streamlit app that reads this bundle: pair lookup with the per-site attention track,
lncRNA -> top miRNAs, miRNA -> lncRNAs, the tissue panel, and a benchmark tab carrying the honest
numbers. It needs the bundle to exist first, so run the above and tell me the row counts.
