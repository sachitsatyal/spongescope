# Deploying the Space

`spaces/README.md` now has your usernames filled in (`sawcheet`, `sachitsatyal`), and
`build_space.py` assembles the Space folder so you are not copying files by hand.

## 1. Upload the model and the bundle

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-phase7c-space.zip" -DestinationPath . -Force

$env:HF_TOKEN = "hf_..."
uv run python scripts\upload_to_hf.py --user sawcheet
```

Get a **write** token at <https://huggingface.co/settings/tokens>. Creates
`sawcheet/spongescope` (model) and `sawcheet/spongescope-demo` (dataset).

## 2. Build the Space folder

```powershell
uv run python scripts\build_space.py --user sawcheet
```

Writes `build/space/` with exactly four files: `README.md`, `requirements.txt`,
`app/streamlit_app.py`, `app/data.py`. Nothing else — not the training code, not dbt, not the
data. A Space that ships the whole repo rebuilds a far larger image on every push.

## 3. Create and push

Create the Space first at <https://huggingface.co/new-space>: name `spongescope`, SDK
**Streamlit**, hardware **CPU basic**. Then:

```powershell
cd build\space
git init
git remote add origin https://huggingface.co/spaces/sawcheet/spongescope
git add . ; git commit -m "SpongeScope demo" ; git push -u origin main
cd ..\..
```

Git will ask for credentials: username `sawcheet`, password = your **HF token**, not your
account password.

## 4. Set the one variable that matters

In the Space: **Settings → Variables and secrets → New variable**

```
SPONGESCOPE_BUNDLE = hf://datasets/sawcheet/spongescope-demo
```

Add it as a *variable*, not a secret — it is not sensitive, and variables are visible in the
build log, which makes a misconfiguration obvious instead of mysterious.

Without it the app looks for `data/demo` on disk, which the Space does not have, and every tab
shows the missing-bundle error.

## On the PowerShell error

`uv run ... --user <your-hf-username>` failed because PowerShell reserves `<` as a redirection
operator. My fault for putting angle-bracket placeholders inside a PowerShell block — every
command from here on uses your real username.

## One thing to decide before you push

The Space will be **public by default**, and it links to the GitHub repo, which is currently
private. Either make the repo public at the same time, or remove the Code link from
`spaces/README.md` until you do — a dead link on the landing page reads worse than no link.
