# Nextflow and DagsHub

## What Nextflow actually adds

Every step already runs as one `uv run` command, and that is how they are run day to day. What a
workflow manager adds is that the **order and the inputs are declared rather than remembered**:
a new machine reproduces the run from one command, and a failed step resumes instead of
restarting from the top.

`main.nf` wires: dbt build -> (RNA-FM embeddings ∥ accessibility) -> site tables -> baselines ->
training (one task per seed) -> benchmark report. The two feature steps are independent, so
Nextflow runs them in parallel without being told to.

**It cannot run on your workstation.** Nextflow needs Bash and Java 17+ and is POSIX-only. It
runs in GitHub Actions (`-profile test`) and on a Kaggle GPU notebook (`-profile kaggle`).

### Profiles differ in what they can afford, not in what they do

| profile | where | training | notes |
|---|---|---|---|
| `test` | GitHub Actions | skipped | proves the DAG wires up and the SQL builds |
| `kaggle` | Kaggle GPU notebook | 3 seeds | 13 GB / 11 h, inside Kaggle's 12 h session cap |
| `local` | WSL, if ever | 1 seed | the 5090 |

Memory and time in the kaggle profile are set just under Kaggle's limits deliberately, so a
failure is ours (a real overrun) rather than theirs (a submit-time rejection that explains
nothing).

Every run writes a timeline, report, trace and DAG into `results/pipeline/`. A run you cannot
account for afterwards is a run you cannot defend, and these cost nothing.

## DagsHub: what moves off the laptop

**The DVC remote.** `data/raw.dvc` is currently a pointer to files that exist on exactly one
machine. Reproducible from `download.py`, but one disk failure from gone, and nobody else can
`dvc pull`.

**MLflow.** Runs live in a local sqlite file. On DagsHub they get a URL you can link from the
README — the difference between "I tracked experiments" and "here are the experiments".

```powershell
$env:DAGSHUB_USER  = "sawcheet"
$env:DAGSHUB_TOKEN = "..."
uv run python scripts\setup_dagshub.py --dry-run
uv run python scripts\setup_dagshub.py
```

Sign up at <https://dagshub.com> and connect the GitHub repo first; the free tier covers both and
takes the repo as-is. Credentials go to `.dvc/config.local` (gitignored); the remote URL goes to
`.dvc/config` and **should** be committed — that is what lets anyone else pull the data.

Then `uv run dvc push` — about 6 GB on the first run.

**One thing to decide now rather than later:** there is no import path for existing MLflow runs.
Re-pointing the tracking URI starts a fresh history, so either accept that the current runs stay
local, or set this up before the next training run.

## Install

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-nextflow-dagshub.zip" -DestinationPath . -Force
uv run ruff check --fix . ; uv run ruff format . ; git add . ; git commit -m "Phase 7: Nextflow pipeline, DagsHub setup" ; git push
```

Nothing here runs locally, so there is nothing to verify on Windows beyond the commit. The
honest way to test `main.nf` is a Kaggle notebook with `-profile kaggle`, and I would do that
only when you next want a full retrain — it is an hour of GPU to prove something that currently
works fine as seven separate commands.
