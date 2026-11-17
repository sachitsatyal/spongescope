# `hf:/` with one slash — the Space is working, the location string was not

The Space builds, runs, and serves. The only failure left was the bundle location.

Look at the error text: `hf:/datasets/sawcheet/spongescope-demo`, one slash. The app did this:

```python
return Bundle.load(Path(directory))  # Path("hf://x") -> "hf:/x"
```

`Path` normalises a doubled separator, the `hf://` prefix check then missed, and the app fell
through to treating it as a local directory called `hf:`. The variable you set was correct the
whole time.

Two changes, because one of them alone would leave the trap in place:

1. `load_bundle` passes the string through untouched — `Bundle.load` decides what it means.
2. `resolve_bundle` accepts `hf:/datasets/` as well as `hf://datasets/`, so a `Path` round-trip
   anywhere else cannot resurrect this.

A test now asserts both spellings resolve to the same repo, with `huggingface_hub` stubbed so it
runs offline.

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-space-fix3.zip" -DestinationPath . -Force

uv run pytest tests\test_demo_data.py -q
uv run python scripts\build_space.py --user sawcheet
```

Check it printed five files, then:

```powershell
uv run python scripts\push_space.py --user sawcheet
```

The Space rebuilds on push. The variable is already set, so this should be the last step — first
load will take a few seconds while it pulls the 12 MB bundle, then it is cached.

## Worth noting

`Uvicorn server started on 0.0.0.0:8501` in your container log means the Dockerfile's port and
bind address were right, and `Running` means the Docker SDK works on free CPU Basic. The
third-party claim that Docker Spaces now need a PRO plan was wrong, at least for this account.
