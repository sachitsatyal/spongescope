# Two fixes

## 1. Twenty lncRNAs are missing from your scores — my bug

`824,934 = 1,293 x 638`, not `1,313 x 638`. Your `--genes 5` trial wrote `part-0000.parquet`
holding 5 genes. The full run saw the file existed and skipped the shard, which was supposed to
hold 25. The other 20 genes were never scored, and nothing complained because the totals still
looked plausible.

My skip check asked "does this file exist" when it should have asked "does this file contain the
genes this shard is for". Now it reads the shard's gene_ids and rescores if they do not match,
and the final summary compares scored pairs against expected and prints `INCOMPLETE` with the
count of missing lncRNAs if they differ.

To fill the gap — about 2-3 minutes, since only shard 0 is rescored:

```powershell
uv run python scripts\precompute_scores.py
```

It should print `shard 1/53: has 5 of 25 genes, rescoring` and then skip the other 52. Expect
**837,694** pairs and `1,313 of 1,313 lncRNAs covered` at the end. Then rebuild the bundle:

```powershell
uv run python scripts\build_demo_bundle.py
```

## 2. The app could not import its own data layer

`streamlit run app/streamlit_app.py` puts `app/` on `sys.path`, not the project root, so
`app.data` does not resolve.

I first fixed this with a `sys.path.insert` at the top of the app — then realised ruff's import
sorter moves imports above that line and breaks it again on the next `ruff check --fix`. A fix
that your own pre-commit hook undoes is not a fix.

So the app imports `data` as a sibling, which is exactly how `streamlit run` resolves it, and
`tests/conftest.py` adds `app/` to the path so the tests import the same module under the same
name. No path juggling, nothing for the formatter to break, and the same command works locally,
in Docker, and on Spaces.

```powershell
uv run pytest tests\test_demo_data.py -q
uv run streamlit run app\streamlit_app.py
```

## Noted, not a problem

`dim_lncrna: no column(s) ['length', 'n_sites', 'cluster_rep']` is the bundle script degrading on
purpose — it keeps the columns that exist and says which it skipped. The demo does not need them.
