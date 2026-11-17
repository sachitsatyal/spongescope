"""Create and push the Space through the Hub API, so git credentials never come into it.

`git push` to huggingface.co needs an access token as the password -- HF disabled account
passwords for git -- and on Windows the credential manager tends to cache the first wrong answer
and keep replaying it. Uploading through the API uses HF_TOKEN directly and sidesteps all of it.

Creates the Space if it does not exist, then uploads the built folder.

    $env:HF_TOKEN = "hf_..."
    uv run python scripts/push_space.py --user sawcheet --dry-run
    uv run python scripts/push_space.py --user sawcheet
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REQUIRED = ("README.md", "requirements.txt", "Dockerfile", "app/streamlit_app.py", "app/data.py")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--space", default="spongescope")
    ap.add_argument("--dataset", default="spongescope-demo")
    ap.add_argument("--folder", type=Path, default=Path("build/space"))
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo_id = f"{args.user}/{args.space}"
    missing = [f for f in REQUIRED if not (args.folder / f).exists()]
    if missing:
        sys.exit(f"{args.folder} is missing {missing}. Run scripts/build_space.py first.")

    print(f"space {repo_id}  (sdk: docker)")
    for f in sorted(args.folder.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            print(f"  {f.relative_to(args.folder).as_posix():28s} {f.stat().st_size / 1e3:7.1f} KB")

    if args.dry_run:
        print("\ndry run; nothing uploaded")
        return

    if not os.environ.get("HF_TOKEN"):
        sys.exit("HF_TOKEN is not set. Create one (write access) at huggingface.co/settings/tokens")

    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(
        repo_id,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )
    api.upload_folder(
        repo_id=repo_id,
        repo_type="space",
        folder_path=str(args.folder),
        ignore_patterns=[".git/*", "**/__pycache__/*"],
        commit_message="SpongeScope demo",
    )

    url = f"https://huggingface.co/spaces/{repo_id}"
    print(f"\npushed -> {url}")
    print(f"""
One step left, and the app will not work without it. At

  {url}/settings

add a variable (not a secret):

  SPONGESCOPE_BUNDLE = hf://datasets/{args.user}/{args.dataset}

Then watch the build log. First boot is slow: the image builds from scratch and the app then
downloads ~12 MB of bundle. After that it is cached.""")


if __name__ == "__main__":
    main()
