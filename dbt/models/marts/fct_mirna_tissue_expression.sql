-- Mean / std expression of each modeled miRNA in each atlas context
-- (biotype x organ system x tissue). Matched to miRBase by mature name.
with a as (
    select * from {{ ref('stg_mirna_tissue_atlas') }}
)

select
    m.mimat_id,
    a.biotype,
    a.organ_system,
    a.tissue,
    max(case when a.metric = 'mean' then a.expr_value end)        as mean_expr,
    max(case when a.metric like 'std%' then a.expr_value end)     as std_expr,
    ln(1 + max(case when a.metric = 'mean' then a.expr_value end)) as log1p_mean_expr
from a
inner join {{ ref('dim_mirna') }} as m
    on m.mirna_name = a.mirna_name
group by m.mimat_id, a.biotype, a.organ_system, a.tissue
