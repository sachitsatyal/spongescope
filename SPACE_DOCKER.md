# Docker Space, not Streamlit Space

Hugging Face **deprecated the Streamlit SDK on 2025-04-30**; Streamlit apps now ship as Docker
Spaces. That is why the form only offers Static, Gradio and Docker. Nothing about the app
changes — only how it is packaged.

## Form answers

| Field | Value |
|---|---|
| Short description | `lncRNA-miRNA interaction prediction with leakage-free evaluation` |
| License | `mit` |
| SDK | **Docker**, template **Blank** |
| Hardware | **CPU Basic** |
| Storage Bucket | off (the bundle comes from the dataset repo) |
| Space Dev Mode | off |
| Visibility | **Public** |

## What changed in this zip

`spaces/README.md` frontmatter is now `sdk: docker` + `app_port: 8501` instead of
`sdk: streamlit`. `spaces/Dockerfile` is new. `build_space.py` copies it and refuses to build a
Docker Space whose README has no `app_port`.

## Three things the Dockerfile does that a normal one would not

**Runs as uid 1000.** Spaces does not run containers as root, so anything written at runtime has
to live somewhere that user owns. `HOME` and the cache paths are set explicitly for that reason.

**Sets `HF_HOME` to a writable path.** The app downloads the demo bundle through
`huggingface_hub` on first load. Without a writable cache the first download fails with a
permission error that does not mention permissions.

**Binds 0.0.0.0:8501 and declares `app_port: 8501`.** Spaces routes traffic to the declared port.
Get this wrong and the image builds cleanly, then the Space sits at "not responding" — which
looks like a broken app rather than a config line.

## Run

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-space-docker.zip" -DestinationPath . -Force
uv run python scripts\build_space.py --user sawcheet
```

Five files now: `Dockerfile`, `README.md`, `requirements.txt`, `app/streamlit_app.py`,
`app/data.py`.

```powershell
cd build\space
git init
git remote add origin https://huggingface.co/spaces/sawcheet/spongescope
git add . ; git commit -m "SpongeScope demo" ; git push -u origin main
cd ..\..
```

Username `sawcheet`, password = your HF **token**.

Then Settings -> Variables and secrets:

```
SPONGESCOPE_BUNDLE = hf://datasets/sawcheet/spongescope-demo
```

## If the build fails

The build log is the first place to look, and it is usually one of three things: the pip install
(a version in `requirements.txt` that does not exist for Python 3.11), the port (app_port not
matching), or the bundle variable (app starts, every tab shows the missing-bundle error).

The first boot is slow — the image builds from scratch and then the app downloads ~12 MB. After
that the bundle is cached and restarts are quick.
