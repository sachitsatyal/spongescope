# Phase 7c — Hugging Face deployment

| File | Purpose |
|---|---|
| `models/spongescope-v1/README.md` | the model card |
| `scripts/upload_to_hf.py` | pushes the model and the bundle to two Hub repos |
| `spaces/README.md` | Space config (YAML frontmatter) + the public description |
| `spaces/requirements.txt` | what the Space installs |
| `app/data.py` | **updated** — a bundle can now be an `hf://datasets/...` location |
| `app/streamlit_app.py` | **updated** — reads `SPONGESCOPE_BUNDLE` from the environment |

## Two repos, not one

```
<user>/spongescope          model repo     weights, config, golden test, model card
<user>/spongescope-demo     dataset repo   the 12 MB parquet bundle
```

The bundle stays out of the Space's own repo on purpose. A Space rebuilds its container on every
code push; 12 MB of parquet living there would be re-uploaded and re-layered each time. As a
dataset it is fetched once into the cache HF already mounts, and a restart does not re-download
it.

## Run

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase7c.zip" -DestinationPath . -Force
uv add huggingface_hub

uv run python scripts\upload_to_hf.py --user <your-hf-username> --dry-run
```

The dry run needs no token: it lists every file and its size, and tells you if the model card is
missing. Then get a **write** token from <https://huggingface.co/settings/tokens> and:

```powershell
$env:HF_TOKEN = "hf_..."
uv run python scripts\upload_to_hf.py --user <your-hf-username>
```

## Then create the Space

1. <https://huggingface.co/new-space> — name `spongescope`, SDK **Streamlit**, hardware **CPU
   basic (free)**.
2. Clone it, copy in `app/`, `spaces/requirements.txt` as `requirements.txt`, and
   `spaces/README.md` as `README.md` (replace `{HF_USER}` and `{GH_USER}` first — the YAML
   frontmatter is what configures the Space, so keep it at the very top).
3. In the Space's **Settings → Variables**, add:
   `SPONGESCOPE_BUNDLE = hf://datasets/<your-hf-username>/spongescope-demo`
4. Push. The Space builds and starts.

Only `app/` and those two files go in the Space — not the training code, not dbt, not the data.

## About the model card

It leads with what the model does not establish, and then with two negative results. That is a
deliberate choice, and worth defending if anyone asks: the AUPR gain is not statistically
significant at this test-set size, the tissue features carried nothing, and the site-supervision
experiment made things worse. A card that omitted those would be making claims the evidence does
not support, and anyone who reproduced the work would find out.

The thing it *can* claim is unusually solid for this problem: the published method it rebuilds
reports AUC ≈ 0.96 under random pair splits, and reaches 0.52 under leakage-free ones. Being able
to show that gap, with the hard-negative design that removes the seed-matching shortcut, is the
actual contribution.
