"""SpongeScope demo.

Reads the precomputed bundle; runs the model live only for a pasted sequence, which is the one
case no lookup can cover. Everything shown here is either a measured value or a calibrated model
score, and the two are labelled differently on purpose.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

# `streamlit run app/streamlit_app.py` puts app/ on sys.path -- not the project root -- so
# data.py is a sibling import, not `app.data`. Keeping it that way means no sys.path juggling,
# and the same command works locally, in Docker and on Hugging Face Spaces. tests/conftest.py
# adds app/ to the path so the tests import the same module by the same name.
from data import Bundle, label_for_lncrna, pair_score, tissue_panel, top_lncrnas, top_mirnas

# Local path by default; on Spaces this is set to hf://datasets/<user>/spongescope-demo so the
# bundle is fetched from the Hub instead of baked into the container image.
BUNDLE_LOCATION = os.environ.get("SPONGESCOPE_BUNDLE", "data/demo")
MODEL_URL = "https://huggingface.co/sawcheet/spongescope"
CODE_URL = "https://github.com/sachitsatyal/spongescope"

st.set_page_config(page_title="SpongeScope", page_icon="🧬", layout="wide")


@st.cache_resource
def load_bundle(location: str) -> Bundle:
    # Deliberately NOT Path(location): Path("hf://x") normalises to "hf:/x", the prefix check
    # then fails, and the app quietly looks for a local directory called "hf:". Bundle.load
    # decides what the string means.
    return Bundle.load(location)


def probability_badge(p: float, known: bool) -> None:
    left, right = st.columns([1, 2])
    left.metric("Predicted probability", f"{p:.3f}")
    if known:
        right.success(
            "**Already supported by CLIP evidence.** This pair is in the training data, so the "
            "score reflects a known interaction rather than a new prediction."
        )
    else:
        right.info(
            "No CLIP evidence for this pair in our data. That is not evidence of absence — "
            "most pairs have simply never been assayed."
        )


def main() -> None:
    st.title("SpongeScope")
    st.caption(
        "lncRNA-miRNA interaction prediction with leakage-free evaluation. "
        "Scores are calibrated; read the Benchmark tab before trusting a number."
    )

    try:
        bundle = load_bundle(BUNDLE_LOCATION)
    except (FileNotFoundError, OSError) as exc:
        # The location is configuration, not something a visitor should be fixing, so the error
        # says what is wrong without inviting anyone to edit it.
        st.error("The demo data could not be loaded. The Space may still be starting up.")
        st.caption(str(exc))
        st.stop()

    with st.sidebar:
        rows = bundle.manifest.get("rows", {})
        st.metric("Scored pairs", f"{rows.get('scores', len(bundle.scores)):,}")
        st.caption(f"{len(bundle.lncrna):,} lncRNAs x {len(bundle.mirna):,} miRNAs")
        st.divider()
        st.markdown(f"[Model card]({MODEL_URL})  \n[Source code]({CODE_URL})")

    lnc_labels = {label_for_lncrna(r): r.gene_id for _, r in bundle.lncrna.iterrows()}
    mir_labels = {
        f"{r.mirna_name} ({r.mimat_id})" if "mirna_name" in bundle.mirna else r.mimat_id: r.mimat_id
        for _, r in bundle.mirna.iterrows()
    }

    pair_tab, lnc_tab, mir_tab, tissue_tab, bench_tab = st.tabs(
        ["Pair lookup", "lncRNA → miRNAs", "miRNA → lncRNAs", "Tissue context", "Benchmark"]
    )

    with pair_tab:
        c1, c2 = st.columns(2)
        gene_label = c1.selectbox("lncRNA", sorted(lnc_labels), key="pair_lnc")
        mir_label = c2.selectbox("miRNA", sorted(mir_labels), key="pair_mir")
        gene_id, mimat_id = lnc_labels[gene_label], mir_labels[mir_label]

        hit = pair_score(bundle, gene_id, mimat_id)
        if hit is None:
            st.warning("This pair was not in the precomputed grid.")
        else:
            known = not bundle.known_pairs[
                (bundle.known_pairs.gene_id == gene_id) & (bundle.known_pairs.mimat_id == mimat_id)
            ].empty
            probability_badge(float(hit.probability), known)
            a, b, c = st.columns(3)
            a.metric("Candidate seed sites", int(hit.n_candidate_sites))
            b.metric("Rank among miRNAs for this lncRNA", int(hit.rank_in_lncrna))
            c.metric("Rank among lncRNAs for this miRNA", int(hit.rank_in_mirna))

    with lnc_tab:
        gene_label = st.selectbox("lncRNA", sorted(lnc_labels), key="rank_lnc")
        k = st.slider("How many", 5, 100, 25, key="k_lnc")
        table = top_mirnas(bundle, lnc_labels[gene_label], k=k)
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.download_button(
            "Download CSV",
            table.to_csv(index=False).encode(),
            f"{lnc_labels[gene_label]}_top_mirnas.csv",
            "text/csv",
        )
        st.caption(
            "At the operating point measured on held-out lncRNAs, testing the top 10 candidates "
            "returns about 2.7 true interactions instead of the ~1 you would get at random."
        )

    with mir_tab:
        mir_label = st.selectbox("miRNA", sorted(mir_labels), key="rank_mir")
        k = st.slider("How many", 5, 100, 25, key="k_mir")
        table = top_lncrnas(bundle, mir_labels[mir_label], k=k)
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.download_button(
            "Download CSV",
            table.to_csv(index=False).encode(),
            f"{mir_labels[mir_label]}_top_lncrnas.csv",
            "text/csv",
        )

    with tissue_tab:
        st.warning(
            "**This panel is measured expression, not a prediction.** Tissue features were "
            "tested as model inputs and carried no signal (every feature within 0.013 of chance; "
            "see Benchmark). What it can tell you is where both molecules are present — useful "
            "for ruling a context out, not for ranking."
        )
        c1, c2 = st.columns(2)
        gene_label = c1.selectbox("lncRNA", sorted(lnc_labels), key="tis_lnc")
        mir_label = c2.selectbox("miRNA", sorted(mir_labels), key="tis_mir")
        panel = tissue_panel(bundle, lnc_labels[gene_label], mir_labels[mir_label])
        if panel.empty:
            st.info("No shared organ systems — one side is missing from its expression atlas.")
        else:
            st.bar_chart(panel.set_index("organ")[["lncRNA", "miRNA", "both"]])
            st.caption(
                "Each side is scaled by its own maximum: the lncRNA is GTEx TPM and the miRNA is "
                "atlas intensity, so absolute values are not comparable. **both** is the smaller "
                "of the two — the organs where neither is the limiting factor."
            )
            st.dataframe(panel, use_container_width=True, hide_index=True)

    with bench_tab:
        st.subheader("What this model does and does not do")
        st.markdown(
            """
**Evaluation is cold-start.** Test lncRNAs share no MMseqs2 sequence cluster with training, and
10% of miRNA seed families are held out entirely. The published method this rebuilds reported
AUC ≈ 0.96 under random pair splits; re-implemented and evaluated this way it reaches **0.52** —
essentially chance. That gap is the splitting, not the architecture.

**Negatives are hard.** Half are seed-matched: the lncRNA contains a 7mer site for the miRNA but
has no CLIP support. Without that, counting seed matches alone scores 0.88 AUROC, because CLIP
peaks carry seed matches by construction.

**Honest headline:** SpongeScope **ranks** better than the baselines — AUROC gains are
statistically significant on 3 of 6 paired comparisons and positive on all 6. A **precision
(AUPR) improvement is not statistically established** at this test-set size. With 149 test
lncRNAs the AUPR confidence interval is +/-0.03 to 0.05, so differences below ~0.05 cannot be
resolved here.
            """
        )
        metrics = pd.DataFrame(
            {
                "group": ["test_cold_lncrna", "test_seed_controlled", "test_cold_both"],
                "AUROC": [0.841, 0.753, 0.853],
                "AUPR": [0.303, 0.312, 0.297],
                "positive rate": [0.096, 0.163, 0.087],
            }
        )
        st.dataframe(metrics, use_container_width=True, hide_index=True)
        st.markdown(
            """
**Calibration** ECE 0.009 — the probabilities mean roughly what they say.
**precision@10** 0.274 per lncRNA against a 0.096 base rate: ~2.7 hits per 10 tested.

**Known limitations.** Tissue context added nothing measurable. Site-level supervision made the
model worse. Both negative results are reported rather than buried. Training labels come from
CLIP experiments in cell lines, so "no evidence" mostly means "never assayed".
            """
        )
        if bundle.manifest.get("model"):
            with st.expander("Model config"):
                st.json(bundle.manifest["model"])


if __name__ == "__main__":
    main()
