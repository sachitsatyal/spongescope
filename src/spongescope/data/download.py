"""Download raw data sources listed in configs/data_sources.yaml."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "configs" / "data_sources.yaml"
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "MANIFEST.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, timeout: int) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0)) or None
        with (
            tmp.open("wb") as f,
            tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as bar,
        ):
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    tmp.replace(dest)


def main() -> None:
    sources = yaml.safe_load(CONFIG.read_text())["sources"]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    for name, src in sources.items():
        dest = RAW_DIR / src["filename"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"[skip] {name}: {dest.name} already exists")
        else:
            print(f"[get ] {name}")
            download(src["url"], dest, timeout=src.get("timeout", 120))

        manifest[name] = {
            "url": src["url"],
            "version": src.get("version"),
            "file": dest.relative_to(ROOT).as_posix(),
            "sha256": sha256(dest),
            "bytes": dest.stat().st_size,
            "downloaded_utc": manifest.get(name, {}).get("downloaded_utc")
            or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest written: {MANIFEST}")


if __name__ == "__main__":
    main()
