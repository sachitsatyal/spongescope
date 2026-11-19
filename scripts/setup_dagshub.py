"""Point DVC and MLflow at DagsHub.

Two things move off the laptop here:

  DVC remote   the ~6 GB of raw data, features and processed parquet that git does not hold.
               Right now `data/raw.dvc` is a pointer to files that exist only on one machine --
               reproducible from download.py, but one disk failure from gone.
  MLflow       runs currently live in a local sqlite file. On DagsHub they get a URL that can be
               linked from the README, which is the difference between "I tracked experiments"
               and "here are the experiments".

DagsHub's free tier covers both and takes the repo as-is.

    $env:DAGSHUB_USER  = "sawcheet"
    $env:DAGSHUB_TOKEN = "..."        # Settings -> Tokens on dagshub.com
    uv run python scripts/setup_dagshub.py --dry-run
    uv run python scripts/setup_dagshub.py
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

REMOTE = "dagshub"


def run(cmd: list[str], *, dry: bool) -> None:
    printable = " ".join(c if "token" not in c.lower() else "***" for c in cmd)
    print(f"  {printable}")
    if dry:
        return
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode:
        sys.exit(f"failed: {printable}\n{result.stderr.strip()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="spongescope")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    user = os.environ.get("DAGSHUB_USER")
    token = os.environ.get("DAGSHUB_TOKEN")
    if not user or not token:
        sys.exit("Set DAGSHUB_USER and DAGSHUB_TOKEN first (dagshub.com -> Settings -> Tokens)")

    base = f"https://dagshub.com/{user}/{args.repo}"
    print(f"DVC remote -> {base}.dvc")
    run(["uv", "run", "dvc", "remote", "add", "-d", "-f", REMOTE, f"{base}.s3"], dry=args.dry_run)
    run(
        ["uv", "run", "dvc", "remote", "modify", REMOTE, "endpointurl", f"{base}.s3"],
        dry=args.dry_run,
    )
    run(
        ["uv", "run", "dvc", "remote", "modify", "--local", REMOTE, "access_key_id", token],
        dry=args.dry_run,
    )
    run(
        ["uv", "run", "dvc", "remote", "modify", "--local", REMOTE, "secret_access_key", token],
        dry=args.dry_run,
    )

    print("\nMLflow tracking:")
    print(f"  MLFLOW_TRACKING_URI={base}.mlflow")
    print(f"  MLFLOW_TRACKING_USERNAME={user}")
    print("  MLFLOW_TRACKING_PASSWORD=<your token>")

    print("""
--local keeps the credentials in .dvc/config.local, which is gitignored. The non-local settings
go in .dvc/config and SHOULD be committed -- that is what lets someone else `dvc pull`.

Then:

  uv run dvc push                      # ~6 GB on the first run
  git add .dvc/config ; git commit -m "DVC remote: DagsHub" ; git push

To move existing MLflow runs off the local sqlite, re-point the tracking URI and re-log; there
is no import path, which is a reason to set this up before the next training run rather than
after.""")


if __name__ == "__main__":
    main()
