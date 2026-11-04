"""Shared helpers for feature computation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = str(ROOT / "configs")


def project_path(rel: str) -> Path:
    return ROOT / rel


def load_table(processed_dir: str, name: str) -> pd.DataFrame:
    return pd.read_parquet(project_path(processed_dir) / f"{name}.parquet")


def clean_rna(seq: str) -> str:
    """Uppercase, T->U, anything that is not ACGU becomes N."""
    return re.sub(r"[^ACGU]", "N", seq.upper().replace("T", "U"))


def window_starts(n: int, window: int, stride: int) -> list[int]:
    """Start positions of overlapping windows that cover [0, n) completely."""
    if n <= window:
        return [0]
    starts = list(range(0, n - window + 1, stride))
    if starts[-1] + window < n:
        starts.append(n - window)
    return starts


def stitch(chunks: list[np.ndarray], starts: list[int], n: int) -> np.ndarray:
    """Average per-position vectors from overlapping windows back to length n."""
    dim = chunks[0].shape[1]
    total = np.zeros((n, dim), dtype=np.float32)
    count = np.zeros((n, 1), dtype=np.float32)
    for chunk, s in zip(chunks, starts, strict=True):
        total[s : s + len(chunk)] += chunk
        count[s : s + len(chunk)] += 1
    if (count == 0).any():
        raise ValueError("windows do not cover the whole sequence")
    return total / count


def write_manifest(path: Path, info: dict) -> None:
    info = {"created_utc": datetime.now(UTC).isoformat(timespec="seconds"), **info}
    path.write_text(json.dumps(info, indent=2, default=str))
