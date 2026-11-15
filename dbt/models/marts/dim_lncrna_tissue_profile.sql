-- Per-lncRNA tissue summary: breadth, peak tissue, and tissue specificity (tau).
-- tau = sum(1 - x_i / max_x) / (n - 1) on log1p TPM; 0 = uniform, 1 = one tissue only.
--
-- Both divisions are guarded with nullif() rather than a surrounding CASE. A CASE cannot protect
-- them: the division sits inside sum(), and the aggregate is computed over the whole group before
-- the CASE chooses a branch, so the division happens for every row regardless of the guard.
-- DuckDB survives that because x/0 yields NULL there; Snowflake raises "Division by zero".
-- nullif() moves the guard to where the division actually happens, and the result is identical
-- on both engines: NULL when a gene has no expression anywhere (max = 0) or only one tissue row
-- (n - 1 = 0).
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
        {{ arg_max('tissue', 'median_tpm') }}                        as top_tissue
    from e
    group by gene_id
)

select
    s.gene_id,
    s.n_tissues,
    s.n_expressed_tissues,
    s.max_tpm,
    s.top_tissue,
    sum(1 - e.log1p_tpm / nullif(s.max_log1p_tpm, 0))
        / nullif(s.n_tissues - 1, 0)                       as tau
from stats as s
inner join e
    on e.gene_id = s.gene_id
group by s.gene_id, s.n_tissues, s.n_expressed_tissues, s.max_tpm, s.top_tissue, s.max_log1p_tpm
