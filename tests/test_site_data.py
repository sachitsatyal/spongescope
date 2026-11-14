import numpy as np
import pandas as pd

from spongescope.data.site_data import PAIR_FEAT_DIM, SITE_FEAT_DIM, SiteCollate, SiteStore
from spongescope.features.sites import build_site_tables


def make_store(tmp_path, use_rnafm=True, use_accessibility=True):
    rng = np.random.default_rng(1)
    b = np.array(list("ACGU"))
    seqs = ["".join(rng.choice(b, n)) for n in (400, 1500)]
    lnc = pd.DataFrame(
        {
            "transcript_id": ["T0", "T1"],
            "sequence": seqs,
            "transcript_length": [len(s) for s in seqs],
        }
    )
    mirs = ["UGAGGUAGUAGGUUGUAUAGUU", "AAAAAAAAAAAAAAAAAAAAAA"]  # let-7a; poly-A -> no sites
    mir = pd.DataFrame({"mimat_id": ["M0", "M1"], "sequence": mirs})
    seqs[1] = seqs[1][:100] + "CUACCUCA" + seqs[1][108:]  # plant a let-7a 8mer
    lnc["sequence"] = seqs
    pairs = pd.DataFrame(
        {
            "pair_id": ["G0|M0", "G1|M0", "G0|M1"],
            "gene_id": ["G0", "G1", "G0"],
            "transcript_id": ["T0", "T1", "T0"],
            "mimat_id": ["M0", "M0", "M1"],
            "label": [0, 1, 0],
        }
    )
    (tmp_path / "rnafm" / "lncrna").mkdir(parents=True)
    (tmp_path / "accessibility").mkdir()
    for t, s in zip(lnc.transcript_id, seqs, strict=True):
        np.save(
            tmp_path / "rnafm" / "lncrna" / f"{t}.npy", rng.random((len(s), 640)).astype(np.float16)
        )
        np.save(tmp_path / "accessibility" / f"{t}.npy", rng.random((len(s), 2)).astype(np.float16))
    np.savez(
        tmp_path / "rnafm" / "mirna.npz",
        **{m: rng.random((22, 640)).astype(np.float16) for m in mir.mimat_id},
    )
    sites, tab = build_site_tables(pairs, lnc, mir, tmp_path / "accessibility", max_sites=4)
    store = SiteStore(
        lnc,
        mir,
        sites,
        tab,
        tmp_path,
        use_rnafm=use_rnafm,
        use_accessibility=use_accessibility,
        window=10,
        max_sites=4,
    )
    return pairs, store


def test_batch_shapes_and_no_site_pair(tmp_path):
    pairs, store = make_store(tmp_path)
    b = SiteCollate(pairs, store).numpy_batch([0, 1, 2])
    assert b["site_tok"].shape[2:] == (21, 642) and b["site_feat"].shape[2] == SITE_FEAT_DIM
    assert b["pair_feat"].shape == (3, PAIR_FEAT_DIM) and b["mir_tok"].shape == (3, 22, 640)
    assert b["site_mask"][1].any()  # planted 8mer
    assert not b["site_mask"][2].any()  # poly-A miRNA -> no sites
    assert np.isfinite(b["site_tok"].astype(np.float32)).all()
    k = int(b["site_mask"][1].sum())
    assert b["tok_mask"][1, :k].any(1).all() and not b["tok_mask"][1, k:].any()


def test_one_hot_ablation(tmp_path):
    pairs, store = make_store(tmp_path, use_rnafm=False, use_accessibility=False)
    b = SiteCollate(pairs, store).numpy_batch([1])
    assert b["site_tok"].shape[-1] == 4 and b["mir_tok"].shape[-1] == 4
    tok = b["site_tok"][0, 0][b["tok_mask"][0, 0]]
    assert (tok.astype(np.float32).sum(1) == 1).all()
