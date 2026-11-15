-- miRNA tissue atlas, wide -> long: one row per (miRNA, biotype, organ system, tissue, metric).
--
-- The two warehouses reach the same shape by different routes, and this is the only model in the
-- project where that is true. DuckDB reshapes the 674 x 2,660 raw table with UNPIVOT. Snowflake's
-- UNPIVOT needs an explicit column list, and writing out 2,656 miRNA names would be a generated
-- file that breaks on every atlas release -- so load_snowflake.py melts it in pandas and writes
-- mirna_tissue_atlas_long, and here Snowflake just reads that.
--
-- Both routes drop NULL measurements: DuckDB's UNPIVOT excludes NULLs unless INCLUDE NULLS is
-- given, and the loader drops non-numeric values, so the row counts agree. The Snowflake branch
-- addresses the table directly rather than through source() so that no sources.yml entry is
-- needed for a table that only exists on one target; the cost is no source freshness on it.
--
-- portable-ok: adapter-dispatched
{% if atlas_is_prereshaped() %}

select
    mirna_name,
    biotype,
    organ_system,
    tissue,
    lower(metric) as metric,
    expr_value
from {{ target.database }}.raw.mirna_tissue_atlas_long

{% else %}

with long as (
    unpivot {{ source('raw', 'mirna_tissue_atlas') }}
    on columns(* exclude ("index", "Biotype", "Organ_system", "Tissue", "Metric"))
    into name mirna_name value expr_value
)

select
    mirna_name,
    "Biotype"       as biotype,
    "Organ_system"  as organ_system,
    "Tissue"        as tissue,
    lower("Metric") as metric,
    expr_value
from long

{% endif %}
