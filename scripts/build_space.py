"""Assemble the Hugging Face Space folder.

A Space is a git repo with a specific shape: README.md carrying YAML frontmatter at the very
top, requirements.txt, and the app. This copies exactly those and nothing else -- no training
code, no dbt project, no data. What is left out matters: a Space that ships the whole repo
rebuilds a much bigger image on every push and exposes code that has no business being public
on a demo.

Usage:
    uv run python scripts/build_space.py --user sawcheet
    uv run python scripts/build_space.py --user sawcheet --out build/space
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
from pathlib import Path

APP_FILES = ("streamlit_app.py", "data.py")


def _force_writable(func, path: str, _exc: object) -> None:
    """Retry a failed delete after clearing the read-only bit.

    Git marks objects under .git read-only, and on Windows that makes os.unlink fail with
    "Access is denied" -- so a stale .git left by an earlier `git init` stops rmtree, the build
    silently keeps the previous output, and the next push uploads the old files. That is exactly
    how a fixed README got re-uploaded unfixed.
    """
    Path(path).chmod(stat.S_IWRITE)
    func(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True, help="Hugging Face username that owns the dataset")
    ap.add_argument("--dataset", default="spongescope-demo")
    ap.add_argument("--app", type=Path, default=Path("app"))
    ap.add_argument("--spaces", type=Path, default=Path("spaces"))
    ap.add_argument("--out", type=Path, default=Path("build/space"))
    args = ap.parse_args()

    readme = args.spaces / "README.md"
    reqs = args.spaces / "requirements.txt"
    dockerfile = args.spaces / "Dockerfile"
    for path in (readme, reqs, dockerfile):
        if not path.exists():
            sys.exit(f"missing {path}")

    text = readme.read_text(encoding="utf-8")
    if not text.startswith("---"):
        sys.exit(
            f"{readme} must begin with the YAML frontmatter block -- it is what configures the "
            "Space, and HF ignores it if anything precedes it."
        )
    if "{HF_USER}" in text or "{GH_USER}" in text:
        print(f"warning: {readme} still contains placeholders")
    for line in text.splitlines():
        if line.startswith("short_description:"):
            value = line.split(":", 1)[1].strip()
            if len(value) > 60:
                sys.exit(
                    f"short_description is {len(value)} characters; the Hub rejects anything over "
                    f"60. Shorten it in {readme}:\n  {value}"
                )
    if "sdk: docker" in text and "app_port:" not in text:
        sys.exit(
            f"{readme} declares the Docker SDK but no app_port. Spaces routes traffic to that "
            "port; without it the image builds and the Space then times out as 'not responding'."
        )

    if args.out.exists():
        shutil.rmtree(args.out, onerror=_force_writable)
    (args.out / "app").mkdir(parents=True)

    for name in APP_FILES:
        source = args.app / name
        if not source.exists():
            sys.exit(f"missing {source}")
        shutil.copy2(source, args.out / "app" / name)
    shutil.copy2(readme, args.out / "README.md")
    shutil.copy2(reqs, args.out / "requirements.txt")
    shutil.copy2(dockerfile, args.out / "Dockerfile")

    bundle = f"hf://datasets/{args.user}/{args.dataset}"
    total = sum(f.stat().st_size for f in args.out.rglob("*") if f.is_file())
    print(f"{args.out} ({total / 1e3:.1f} KB)")
    for f in sorted(args.out.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(args.out).as_posix()}")

    print(
        f"""
Next:

  uv run python scripts/push_space.py --user {args.user}

That creates the Space if needed and uploads this folder through the Hub API. Do NOT use git
here -- Hugging Face disabled password authentication, and on Windows the credential manager
caches the first failure and replays it.

The Space also needs this variable set once, under Settings -> Variables and secrets:

  SPONGESCOPE_BUNDLE = {bundle}

Without it the app looks for data/demo on disk, which the Space does not have, and every tab
shows the missing-bundle error."""
    )


if __name__ == "__main__":
    main()
