-- Per-lncRNA tissue summary: breadth, peak tissue, and tissue specificity (tau).
-- tau = sum(1 - x_i / max_x) / (n - 1) on log1p TPM; 0 = uniform, 1 = one tissue only.
with e as (
    select * from {{ ref('fct_lncrna_tissue_expression') }}
),

stats as (
    select
        gene_id,
        count(*)                                           as n_tissues,
        sum(case when is_expressed then 1 else 0 end)      as n_expressed_tissues,
        max(log1p_tpm)                                     as max_log1p_tpm,
        max(median_tpm)                                    as max_tpm,
        arg_max(tissue, median_tpm)                        as top_tissue
    from e
    group by gene_id
)

select
    s.gene_id,
    s.n_tissues,
    s.n_expressed_tissues,
    s.max_tpm,
    s.top_tissue,
    case
        when s.max_log1p_tpm = 0 then null
        else sum(1 - e.log1p_tpm / s.max_log1p_tpm) / (s.n_tissues - 1)
    end as tau
from stats as s
inner join e
    on e.gene_id = s.gene_id
group by s.gene_id, s.n_tissues, s.n_expressed_tissues, s.max_tpm, s.top_tissue, s.max_log1p_tpm
