-- GTEx v10 median TPM for each modeled lncRNA in each of the 54 tissues.
-- PAR_Y duplicates are dropped so (gene_id, tissue) is unique.
with gtex as (
    select
        split_part(gene_id_versioned, '.', 1) as gene_id,
        tissue,
        median_tpm
    from {{ source('raw', 'gtex_median_tpm') }}
    where gene_id_versioned not like '%PAR_Y%'
)

select
    d.gene_id,
    g.tissue,
    g.median_tpm,
    ln(1 + g.median_tpm)                         as log1p_tpm,
    g.median_tpm >= {{ var('expressed_tpm') }}   as is_expressed
from {{ ref('dim_lncrna') }} as d
inner join gtex as g
    on g.gene_id = d.gene_id
