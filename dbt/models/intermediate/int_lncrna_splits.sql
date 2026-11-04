-- Cold-start lncRNA split: whole sequence clusters go to train / val / test.
-- Clusters are shuffled deterministically, then filled until each split holds
-- train_frac / val_frac / rest of the positive pairs.
with genes as (
    select gene_id, count(*) as n_pos
    from {{ ref('int_positive_pairs') }}
    group by gene_id
),

gene_clusters as (
    select
        g.gene_id,
        g.n_pos,
        coalesce(c.cluster_id, g.gene_id) as cluster_id
    from genes as g
    left join {{ ref('stg_lnc_clusters') }} as c
        on c.gene_id = g.gene_id
),

clusters as (
    select
        cluster_id,
        sum(n_pos) as n_pos,
        count(*)   as n_genes,
        {{ stable_uniform("cluster_id", var('seed') ~ '_split') }} as u
    from gene_clusters
    group by cluster_id
),

ordered as (
    select
        *,
        coalesce(
            sum(n_pos) over (
                order by u, cluster_id
                rows between unbounded preceding and 1 preceding
            ),
            0
        ) as cum_before,
        sum(n_pos) over () as total_pos
    from clusters
)

select
    gc.gene_id,
    gc.cluster_id,
    o.n_genes as cluster_size,
    case
        when o.cum_before < {{ var('train_frac') }} * o.total_pos then 'train'
        when o.cum_before < ({{ var('train_frac') }} + {{ var('val_frac') }}) * o.total_pos then 'val'
        else 'test'
    end as lncrna_split
from gene_clusters as gc
inner join ordered as o
    on o.cluster_id = gc.cluster_id
