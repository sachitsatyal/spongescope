"""RNA-FM per-nucleotide embeddings (frozen model, cached to disk).

Outputs (under data/features/rnafm/):
  lncrna/<transcript_id>.npy   float16, shape (length, 640)
  lncrna_mean.npz              ids + mean-pooled (n, 640)   -> graph model node features
  mirna.npz                    one (length, 640) array per MIMAT id
  mirna_mean.npz               ids + mean-pooled (n, 640)
  MANIFEST.json

Re-running skips lncRNAs whose file already exists (safe to resume).
"""

from __future__ import annotations

import time
from pathlib import Path

import fm
import hydra
import numpy as np
import requests
import torch
from omegaconf import DictConfig, OmegaConf
from tqdm import tqdm

from spongescope.features.common import (
    clean_rna,
    load_table,
    project_path,
    stitch,
    window_starts,
    write_manifest,
)


def ensure_weights(url: str, expected_bytes: int) -> Path:
    """Put RNA-FM_pretrained.pth where the fm package looks (torch hub cache) before loading.

    fm only downloads when the file is missing, so a complete local copy bypasses its server.
    """
    ckpt = Path(torch.hub.get_dir()) / "checkpoints" / "RNA-FM_pretrained.pth"
    if ckpt.exists() and ckpt.stat().st_size == expected_bytes:
        return ckpt
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    tmp = ckpt.with_suffix(".part")
    print(f"downloading RNA-FM weights from {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as f, tqdm(total=expected_bytes, unit="B", unit_scale=True) as bar:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    if tmp.stat().st_size != expected_bytes:
        raise RuntimeError(f"weights size {tmp.stat().st_size} != expected {expected_bytes}")
    tmp.replace(ckpt)
    return ckpt


def load_model(device: torch.device):
    model, alphabet = fm.pretrained.rna_fm_t12()
    model.eval().to(device)
    return model, alphabet.get_batch_converter()


@torch.no_grad()
def embed_batch(
    model, converter, seqs: list[str], layer: int, device, fp16: bool
) -> list[np.ndarray]:
    """Return one (len(seq), dim) float32 array per input sequence (BOS/EOS removed)."""
    _, _, tokens = converter([(str(i), s) for i, s in enumerate(seqs)])
    tokens = tokens.to(device)
    with torch.autocast(
        device_type=device.type, dtype=torch.float16, enabled=fp16 and device.type == "cuda"
    ):
        out = model(tokens, repr_layers=[layer])
    reps = out["representations"][layer].float().cpu().numpy()
    return [reps[i, 1 : 1 + len(s)] for i, s in enumerate(seqs)]


def embed_long(model, converter, seq: str, cfg, device) -> np.ndarray:
    starts = window_starts(len(seq), cfg.window, cfg.stride)
    chunks: list[np.ndarray] = []
    for b in range(0, len(starts), cfg.batch_size):
        batch_starts = starts[b : b + cfg.batch_size]
        windows = [seq[s : s + cfg.window] for s in batch_starts]
        chunks.extend(embed_batch(model, converter, windows, cfg.layer, device, cfg.fp16))
    return stitch(chunks, starts, len(seq))


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="features")
def main(cfg: DictConfig) -> None:
    rc = cfg.rnafm
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device} | config: {OmegaConf.to_container(rc)}")
    if device.type == "cpu":
        print("WARNING: no GPU found - this will be very slow.")

    out_dir = project_path(cfg.paths.features) / "rnafm"
    lnc_dir = out_dir / "lncrna"
    lnc_dir.mkdir(parents=True, exist_ok=True)

    lnc = load_table(cfg.paths.processed, "dim_lncrna")
    mir = load_table(cfg.paths.processed, "dim_mirna")
    print(f"{len(lnc):,} lncRNAs ({lnc.transcript_length.sum():,} nt), {len(mir):,} miRNAs")

    print(f"weights: {ensure_weights(rc.weights_url, rc.weights_bytes)}")
    model, converter = load_model(device)
    t0 = time.time()

    # --- miRNAs (short: one batch of whole sequences at a time) ---
    mir_arrays: dict[str, np.ndarray] = {}
    ids, seqs = list(mir.mimat_id), [clean_rna(s) for s in mir.sequence]
    for b in tqdm(range(0, len(ids), 64), desc="miRNA"):
        embs = embed_batch(model, converter, seqs[b : b + 64], rc.layer, device, rc.fp16)
        for i, e in zip(ids[b : b + 64], embs, strict=True):
            mir_arrays[i] = e.astype(np.float16)
    np.savez(out_dir / "mirna.npz", **mir_arrays)
    np.savez(
        out_dir / "mirna_mean.npz",
        ids=np.array(ids),
        emb=np.stack([mir_arrays[i].astype(np.float32).mean(0) for i in ids]),
    )

    # --- lncRNAs (long: overlapping windows, stitched) ---
    lnc = lnc.sort_values("transcript_length")
    means = {}
    for tid, seq in tqdm(
        zip(lnc.transcript_id, lnc.sequence, strict=True), total=len(lnc), desc="lncRNA"
    ):
        path = lnc_dir / f"{tid}.npy"
        if path.exists():
            means[tid] = np.load(path).astype(np.float32).mean(0)
            continue
        emb = embed_long(model, converter, clean_rna(seq), rc, device)
        np.save(path, emb.astype(np.float16))
        means[tid] = emb.mean(0)
    tids = list(lnc.transcript_id)
    np.savez(
        out_dir / "lncrna_mean.npz", ids=np.array(tids), emb=np.stack([means[t] for t in tids])
    )

    write_manifest(
        out_dir / "MANIFEST.json",
        {
            "model": "RNA-FM t12 (rna-fm package, frozen)",
            "layer": rc.layer,
            "window": rc.window,
            "stride": rc.stride,
            "dtype": "float16",
            "n_lncrna": len(tids),
            "n_mirna": len(ids),
            "minutes": round((time.time() - t0) / 60, 1),
        },
    )
    print(f"done in {(time.time() - t0) / 60:.1f} min -> {out_dir}")


if __name__ == "__main__":
    main()
