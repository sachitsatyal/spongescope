"""Publish the model and the demo bundle to the Hugging Face Hub.

Two repos, because they are different kinds of thing with different lifetimes:

  <user>/spongescope          model repo    weights, config, golden test, model card
  <user>/spongescope-demo     dataset repo  the parquet bundle the Space reads

Keeping the bundle out of the Space's own repo matters: a Space rebuilds its container on every
code push, and 12 MB of parquet in that repo would be re-uploaded and re-layered each time. As a
dataset it is fetched once into the cache HF already mounts.

Needs a token with write access: https://huggingface.co/settings/tokens

    $env:HF_TOKEN = "hf_..."
    uv run python scripts/upload_to_hf.py --user <your-hf-username> --dry-run
    uv run python scripts/upload_to_hf.py --user <your-hf-username>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MODEL_FILES = ("model.safetensors", "config.json", "golden.json", "README.md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True, help="your Hugging Face username or org")
    ap.add_argument("--model-dir", type=Path, default=Path("models/spongescope-v1"))
    ap.add_argument("--bundle-dir", type=Path, default=Path("data/demo"))
    ap.add_argument("--model-repo", default="spongescope")
    ap.add_argument("--data-repo", default="spongescope-demo")
    ap.add_argument("--private", action="store_true", help="create the repos private")
    ap.add_argument("--dry-run", action="store_true", help="list what would be uploaded")
    args = ap.parse_args()

    model_repo = f"{args.user}/{args.model_repo}"
    data_repo = f"{args.user}/{args.data_repo}"

    model_files = [args.model_dir / f for f in MODEL_FILES if (args.model_dir / f).exists()]
    bundle_files = sorted(args.bundle_dir.glob("*.parquet"))
    manifest = args.bundle_dir / "manifest.json"
    if manifest.exists():
        bundle_files.append(manifest)

    missing = [f for f in MODEL_FILES if not (args.model_dir / f).exists()]
    print(f"model repo {model_repo}")
    for f in model_files:
        print(f"  {f.name:24s} {f.stat().st_size / 1e6:8.2f} MB")
    if missing:
        print(f"  not found (skipping): {missing}")
    print(f"\ndataset repo {data_repo}")
    for f in bundle_files:
        print(f"  {f.name:24s} {f.stat().st_size / 1e6:8.2f} MB")
    total = sum(f.stat().st_size for f in [*model_files, *bundle_files]) / 1e6
    print(f"\n{total:.1f} MB total")

    if "README.md" in missing:
        print("\nNo model card. A model repo without one is the thing reviewers notice first.")

    if args.dry_run:
        print("\ndry run; nothing uploaded")
        return

    if not os.environ.get("HF_TOKEN"):
        sys.exit("HF_TOKEN is not set. Create one at https://huggingface.co/settings/tokens")

    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])

    api.create_repo(model_repo, repo_type="model", private=args.private, exist_ok=True)
    api.upload_folder(
        repo_id=model_repo,
        repo_type="model",
        folder_path=str(args.model_dir),
        commit_message="SpongeScope v1",
    )
    print(f"uploaded -> https://huggingface.co/{model_repo}")

    api.create_repo(data_repo, repo_type="dataset", private=args.private, exist_ok=True)
    api.upload_folder(
        repo_id=data_repo,
        repo_type="dataset",
        folder_path=str(args.bundle_dir),
        allow_patterns=["*.parquet", "manifest.json"],
        commit_message="Demo bundle",
    )
    print(f"uploaded -> https://huggingface.co/datasets/{data_repo}")
    print(f"\nSet the Space to read it:\n  SPONGESCOPE_BUNDLE=hf://datasets/{data_repo}")


if __name__ == "__main__":
    main()
