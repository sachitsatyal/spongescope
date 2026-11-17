"""Score every (lncRNA, miRNA) pair once, so the demo can browse instead of compute.

The free Hugging Face Spaces tier is CPU-only. A cached pair takes ~5 ms, which is fine for one
lookup and hopeless for "rank 638 miRNAs against this lncRNA" on every page load. So the full
grid is scored once here and the demo reads a parquet.

Scope: 1,313 lncRNAs x 638 miRNAs = ~838k pairs. At ~5 ms each that is roughly 70 minutes on CPU,
single-threaded. It is a one-off, it is resumable, and `--genes` runs a small slice first so you
find out in two minutes whether the whole thing will work.

Output: data/demo/scores/part-*.parquet, one shard per N genes, each with
    gene_id, transcript_id, mimat_id, probability, n_candidate_sites
Shards exist so an interrupted run resumes instead of restarting.

Usage:
    uv run python scripts/precompute_scores.py --check
    uv run python scripts/precompute_scores.py --genes 5
    uv run python scripts/precompute_scores.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


def load_inputs(db: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """lncRNA transcripts (with sequence) and miRNAs (with sequence), from the marts."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        lnc = con.execute(
            "select d.gene_id, d.transcript_id, t.sequence "
            "from marts.dim_lncrna as d "
            "inner join staging.stg_lncrna_transcripts as t "
            "    on t.transcript_id = d.transcript_id "
            "order by d.gene_id"
        ).df()
        mir = con.execute(
            "select m.mimat_id, m.mirna_name, s.sequence "
            "from marts.dim_mirna as m "
            "inner join staging.stg_mirna as s on s.mimat_id = m.mimat_id "
            "order by m.mimat_id"
        ).df()
    finally:
        con.close()
    return lnc, mir


def load_mirna_embeddings(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/spongescope.duckdb"))
    ap.add_argument("--model", type=Path, default=Path("models/spongescope-v1"))
    ap.add_argument("--features", type=Path, default=Path("data/features"))
    ap.add_argument("--out", type=Path, default=Path("data/demo/scores"))
    ap.add_argument("--genes", type=int, default=None, help="only this many lncRNAs (a trial run)")
    ap.add_argument("--shard-size", type=int, default=25, help="genes per output shard")
    ap.add_argument("--check", action="store_true", help="report what is available, score nothing")
    args = ap.parse_args()

    lnc, mir = load_inputs(args.db)
    print(f"{len(lnc):,} lncRNA transcripts, {len(mir):,} miRNAs -> {len(lnc) * len(mir):,} pairs")

    emb_dir = args.features / "rnafm" / "lncrna"
    acc_dir = args.features / "accessibility"
    mir_emb_path = args.features / "rnafm" / "mirna.npz"

    missing_emb = [t for t in lnc["transcript_id"] if not (emb_dir / f"{t}.npy").exists()]
    missing_acc = [t for t in lnc["transcript_id"] if not (acc_dir / f"{t}.npy").exists()]
    print(f"  embeddings present: {len(lnc) - len(missing_emb):,}/{len(lnc):,}")
    print(f"  accessibility present: {len(lnc) - len(missing_acc):,}/{len(lnc):,}")
    if not mir_emb_path.exists():
        sys.exit(f"missing miRNA embeddings: {mir_emb_path}")

    if args.check:
        if missing_emb:
            print(f"  first missing embedding: {missing_emb[0]}")
        print("\ncheck only; nothing scored")
        return

    from spongescope.inference import SpongeScope

    model = SpongeScope.load(args.model)
    mir_emb = load_mirna_embeddings(mir_emb_path)
    print(f"model loaded from {args.model}; {len(mir_emb):,} miRNA embeddings")

    usable = lnc[~lnc["transcript_id"].isin(set(missing_emb) | set(missing_acc))]
    if args.genes:
        usable = usable.head(args.genes)
    print(f"scoring {len(usable):,} lncRNAs x {len(mir):,} miRNAs")

    args.out.mkdir(parents=True, exist_ok=True)
    shards = [usable.iloc[i : i + args.shard_size] for i in range(0, len(usable), args.shard_size)]
    started = time.time()
    done_pairs = 0

    for n, shard in enumerate(shards):
        path = args.out / f"part-{n:04d}.parquet"
        expected = set(shard["gene_id"])
        if path.exists():
            # Check WHAT is in the shard, not just that the file exists. A trial run
            # (--genes 5) writes a part-0000 holding 5 genes where the full run expects 25;
            # trusting the filename alone silently drops the other 20 and the totals still
            # look plausible. This is how 824,934 pairs appeared instead of 837,694.
            have = set(pd.read_parquet(path, columns=["gene_id"])["gene_id"])
            if have == expected:
                print(f"  shard {n + 1}/{len(shards)}: complete, skipping")
                continue
            print(
                f"  shard {n + 1}/{len(shards)}: has {len(have)} of {len(expected)} genes, "
                "rescoring"
            )

        rows = []
        for _, gene in shard.iterrows():
            lnc_emb = np.load(emb_dir / f"{gene.transcript_id}.npy")
            acc = np.load(acc_dir / f"{gene.transcript_id}.npy")
            for _, m in mir.iterrows():
                if m.mimat_id not in mir_emb:
                    continue
                pred = model.predict(
                    gene.sequence,
                    m.sequence,
                    lncrna_embedding=lnc_emb,
                    mirna_embedding=mir_emb[m.mimat_id],
                    accessibility=acc,
                )
                rows.append(
                    {
                        "gene_id": gene.gene_id,
                        "transcript_id": gene.transcript_id,
                        "mimat_id": m.mimat_id,
                        "probability": pred.probability,
                        "n_candidate_sites": pred.n_candidate_sites,
                    }
                )
            done_pairs += len(mir)

        pd.DataFrame(rows).to_parquet(path, index=False)
        elapsed = time.time() - started
        rate = done_pairs / elapsed if elapsed else 0
        remaining = (len(usable) * len(mir) - done_pairs) / rate if rate else 0
        print(
            f"  shard {n + 1}/{len(shards)}: {len(rows):,} rows, "
            f"{rate:,.0f} pairs/s, ~{remaining / 60:.0f} min left"
        )

    parts = sorted(args.out.glob("part-*.parquet"))
    scored = pd.concat([pd.read_parquet(p, columns=["gene_id"]) for p in parts])
    genes_done = scored["gene_id"].nunique()
    expected_pairs = len(usable) * len(mir)
    print(f"\n{len(parts)} shard(s), {len(scored):,} scored pairs in {args.out}")
    print(f"{genes_done:,} of {len(usable):,} lncRNAs covered")
    if len(scored) != expected_pairs:
        missing = set(usable["gene_id"]) - set(scored["gene_id"])
        print(
            f"INCOMPLETE: expected {expected_pairs:,} pairs, have {len(scored):,}. "
            f"{len(missing)} lncRNA(s) missing. Re-run to fill them in."
        )


if __name__ == "__main__":
    main()
