# short_description was 64 characters; the Hub allows 60

`push_space.py` validated the README against the Hub before uploading, which is why the error
names the exact field and limit instead of failing somewhere less obvious.

Changed to **"Leakage-free lncRNA-miRNA interaction prediction"** (48 characters) — which reads
better anyway, since it leads with the thing that makes the project worth looking at.

`build_space.py` now checks the length locally, so the next one of these is caught before a
network call rather than by the API.

The Space itself was created before the upload failed, so it exists and is empty. Re-running is
safe; `exist_ok=True` uploads into it.

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-space-fix.zip" -DestinationPath . -Force

uv run python scripts\build_space.py --user sawcheet
uv run python scripts\push_space.py --user sawcheet
```

Then at <https://huggingface.co/spaces/sawcheet/spongescope/settings>, add a **variable**:

```
SPONGESCOPE_BUNDLE = hf://datasets/sawcheet/spongescope-demo
```

And clean up the abandoned git repo:

```powershell
Remove-Item -Recurse -Force build\space\.git -ErrorAction SilentlyContinue
```
