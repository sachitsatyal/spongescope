-- Final modeling table: one row per (lncRNA gene, miRNA) pair with label and split.
--   split:      train / val / test (cold lncRNA, by sequence cluster)
--   eval_group: for test rows, cold_lncrna (miRNA seen in training) or cold_both
-- Train/val pairs that use a held-out miRNA are dropped so cold_both stays clean.
with pairs as (
    select
        gene_id, transcript_id, mimat_id, label, pair_type,
        n_sites, max_clip_exp_num, n_cell_contexts, cell_contexts
    from {{ ref('int_positive_pairs') }}

    union all

    select
        gene_id, transcript_id, mimat_id, label, pair_type,
        cast(null as bigint), cast(null as bigint), cast(null as bigint), cast(null as varchar)
    from {{ ref('int_negative_pairs') }}
),

labelled as (
    select
        p.gene_id || '|' || p.mimat_id as pair_id,
        p.*,
        s.cluster_id,
        s.lncrna_split,
        h.is_holdout as mirna_holdout,
        case
            when s.lncrna_split = 'test' then 'test'
            when h.is_holdout then 'excluded'
            else s.lncrna_split
        end as split,
        case
            when s.lncrna_split = 'test' and h.is_holdout then 'cold_both'
            when s.lncrna_split = 'test' then 'cold_lncrna'
        end as eval_group
    from pairs as p
    inner join {{ ref('int_lncrna_splits') }} as s
        on s.gene_id = p.gene_id
    inner join {{ ref('int_mirna_holdout') }} as h
        on h.mimat_id = p.mimat_id
)

select *
from labelled
where split <> 'excluded'
