-- miRNATissueAtlas 2025 reshaped from wide (one column per miRNA) to long.
with long as (
    unpivot {{ source('raw', 'mirna_tissue_atlas') }}
    on columns(* exclude ("index", "Biotype", "Organ_system", "Tissue", "Metric"))
    into name mirna_name value expr_value
)

select
    "Biotype"       as biotype,
    "Organ_system"  as organ_system,
    "Tissue"        as tissue,
    lower("Metric") as metric,
    mirna_name,
    cast(expr_value as double) as expr_value
from long
