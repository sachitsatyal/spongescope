-- Negatives: for every lncRNA gene, negative_ratio x (its positive count) miRNAs it has
-- no CLIP evidence with, drawn only from miRNAs that appear in positives.
--   * half "degree_matched": weighted by miRNA degree (Efraimidis-Spirakis keys), so popular
--     miRNAs are frequent in negatives too and "popular miRNA = positive" is not a shortcut
--   * half "random": uniform
-- Per-lncRNA 1:ratio balance also removes the "lncRNA degree" shortcut.
-- Hub lncRNAs may get fewer negatives than the ratio (not enough candidate miRNAs).
{% set ratio = var('negative_ratio') %}
{% set seed = var('seed') %}

with pos as (
    select gene_id, transcript_id, mimat_id
    from {{ ref('int_positive_pairs') }}
),

genes as (
    select gene_id, min(transcript_id) as transcript_id, count(*) as n_pos
    from pos
    group by gene_id
),

mirs as (
    select mimat_id, count(*) as mir_degree
    from pos
    group by mimat_id
),

candidates as (
    select
        g.gene_id,
        g.transcript_id,
        g.n_pos,
        m.mimat_id,
        m.mir_degree,
        {{ stable_uniform("g.gene_id || '|' || m.mimat_id", seed ~ '_w') }} as u_weighted,
        {{ stable_uniform("g.gene_id || '|' || m.mimat_id", seed ~ '_r') }} as u_random
    from genes as g
    cross join mirs as m
    where not exists (
        select 1 from pos as p
        where p.gene_id = g.gene_id and p.mimat_id = m.mimat_id
    )
),

weighted_ranked as (
    select
        *,
        row_number() over (
            partition by gene_id
            order by pow(u_weighted, 1.0 / mir_degree) desc, mimat_id
        ) as rk
    from candidates
),

weighted_pick as (
    select gene_id, transcript_id, mimat_id, n_pos
    from weighted_ranked
    where rk <= ceil(n_pos * {{ ratio }} / 2.0)
),

random_ranked as (
    select
        c.*,
        row_number() over (partition by c.gene_id order by c.u_random, c.mimat_id) as rk
    from candidates as c
    where not exists (
        select 1 from weighted_pick as w
        where w.gene_id = c.gene_id and w.mimat_id = c.mimat_id
    )
),

random_pick as (
    select gene_id, transcript_id, mimat_id
    from random_ranked
    where rk <= n_pos * {{ ratio }} - ceil(n_pos * {{ ratio }} / 2.0)
)

select gene_id, transcript_id, mimat_id, 0 as label, 'degree_matched' as pair_type
from weighted_pick
union all
select gene_id, transcript_id, mimat_id, 0 as label, 'random' as pair_type
from random_pick
