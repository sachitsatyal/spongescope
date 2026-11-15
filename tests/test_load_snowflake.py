"""The atlas reshape is the one piece of the Snowflake path not covered by a dbt test.

On Snowflake `stg_mirna_tissue_atlas` is a passthrough, so if the reshape is wrong nothing in dbt
catches it -- the join to int_mirna_name_map just returns zero rows. These tests stand in for the
dbt test that cannot exist there.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from spongescope.data.load_snowflake import normalize, normalize_frame, reshape_atlas


def wide() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index": [0, 1, 2],
            "Biotype": ["tissue", "tissue", "cell_line"],
            "Organ_system": ["brain", "brain", "blood"],
            "Tissue": ["cortex", "cortex", "k562"],
            "Metric": ["mean", "std", "mean"],
            "hsa-miR-99a-5p": [1.5, 0.2, 3.0],
            "hsa-let-7a-5p": [2.5, 0.4, np.nan],
        }
    )


def test_mirna_names_survive_verbatim() -> None:
    """The whole point: int_mirna_name_map joins on the original name, not a normalized one."""
    out = reshape_atlas(wide())
    assert set(out["MIRNA_NAME"]) == {"hsa-miR-99a-5p", "hsa-let-7a-5p"}
    assert "HSA_MIR_99A_5P" not in set(out["MIRNA_NAME"])


def test_id_columns_normalized_and_index_dropped() -> None:
    out = reshape_atlas(wide())
    assert list(out.columns) == [
        "BIOTYPE",
        "ORGAN_SYSTEM",
        "TISSUE",
        "METRIC",
        "MIRNA_NAME",
        "EXPR_VALUE",
    ]
    assert "INDEX" not in out.columns


def test_nulls_dropped_to_match_duckdb_unpivot() -> None:
    """DuckDB's UNPIVOT excludes NULLs unless INCLUDE NULLS is given, so row counts must agree."""
    out = reshape_atlas(wide())
    assert len(out) == 5  # 3 rows x 2 miRNAs, minus the one NaN
    assert out["EXPR_VALUE"].notna().all()


def test_metric_case_left_to_the_model() -> None:
    """The model applies lower(metric) on both targets, so the loader must not pre-lower it."""
    out = reshape_atlas(wide())
    assert set(out["METRIC"]) == {"mean", "std"}


def test_normalize_matches_the_jinja_macro() -> None:
    assert normalize("miRNAid") == "MIRNAID"
    assert normalize("cellline/tissue") == "CELLLINE_TISSUE"
    assert normalize("geneID") == "GENEID"
    assert normalize("Organ_system") == "ORGAN_SYSTEM"
    assert normalize("hsa-miR-99a-5p") == "HSA_MIR_99A_5P"


def test_reserved_words_survive_normalization() -> None:
    """They are written quoted, so a reserved word just becomes its upper-case self."""
    assert normalize("start") == "START"
    assert normalize("end") == "END"


def test_normalize_frame_rejects_collisions() -> None:
    df = pd.DataFrame(columns=["gene id", "gene_id"])
    try:
        normalize_frame(df)
    except ValueError as exc:
        assert "collide" in str(exc)
    else:
        raise AssertionError("expected a collision error")
