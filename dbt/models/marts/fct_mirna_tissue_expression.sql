-- Mean / std expression of each modeled miRNA in each atlas context
-- (biotype x organ system x tissue). Joined through int_mirna_name_map, which handles the
-- un-suffixed older names the atlas uses for single-arm miRNAs.
with a as (
    select * from {{ ref('stg_mirna_tissue_atlas') }}
)

select
    nm.mimat_id,
    a.biotype,
    a.organ_system,
    a.tissue,
    max(case when a.metric = 'mean' then a.expr_value end)         as mean_expr,
    max(case when a.metric like 'std%' then a.expr_value end)      as std_expr,
    ln(1 + max(case when a.metric = 'mean' then a.expr_value end)) as log1p_mean_expr
from a
inner join {{ ref('int_mirna_name_map') }} as nm
    on nm.atlas_name = a.mirna_name
group by nm.mimat_id, a.biotype, a.organ_system, a.tissue
