-- Negatives: for every lncRNA gene, negative_ratio x (its positive count) miRNAs with no CLIP
-- evidence, drawn only from miRNAs that appear in positives. Three kinds:
--   * "seed_matched" (hard_negative_frac): the lncRNA contains a canonical 7mer site
--     (7mer-m8 or 7mer-A1) for the miRNA but CLIP never saw binding. ENCORI positives carry
--     seed sites by construction (94% vs 30% of random negatives), so without these a model
--     can win by seed matching alone.
--   * "degree_matched": weighted by miRNA degree (Efraimidis-Spirakis keys)
--   * "random": uniform
-- Per-lncRNA balance removes the lncRNA-degree shortcut. If a lncRNA has too few seed-matched
-- candidates, the shortfall is filled by the other two kinds.
{% set ratio = var('negative_ratio') %}
{% set seed = var('seed') %}
{% set hard = var('hard_negative_frac') %}

with pos as (
    select gene_id, transcript_id, mimat_id
    from {{ ref('int_positive_pairs') }}
),

genes as (
    select
        gene_id,
        min(transcript_id)                                   as transcript_id,
        count(*)                                             as n_pos,
        count(*) * {{ ratio }}                               as n_total,
        cast(round(count(*) * {{ ratio }} * {{ hard }}) as bigint) as n_hard_target
    from pos
    group by gene_id
),

mir_sites as (
    select
        p.mimat_id,
        count(*)                                                          as mir_degree,
        reverse(translate(substr(min(m.sequence), 2, 7), 'ACGU', 'UGCA'))       as site_m8,
        reverse(translate(substr(min(m.sequence), 2, 6), 'ACGU', 'UGCA')) || 'A' as site_a1
    from pos as p
    inner join {{ ref('stg_mirna') }} as m
        on m.mimat_id = p.mimat_id
    group by p.mimat_id
),

candidates as (
    select
        g.gene_id,
        g.transcript_id,
        g.n_total,
        g.n_hard_target,
        ms.mimat_id,
        ms.mir_degree,
        (contains(r.sequence, ms.site_m8) or contains(r.sequence, ms.site_a1)) as has_site,
        {{ stable_uniform("g.gene_id || '|' || ms.mimat_id", seed ~ '_h') }} as u_hard,
        {{ stable_uniform("g.gene_id || '|' || ms.mimat_id", seed ~ '_w') }} as u_weighted,
        {{ stable_uniform("g.gene_id || '|' || ms.mimat_id", seed ~ '_r') }} as u_random
    from genes as g
    inner join {{ ref('int_gene_representative') }} as r
        on r.gene_id = g.gene_id
    cross join mir_sites as ms
    where not exists (
        select 1 from pos as p
        where p.gene_id = g.gene_id and p.mimat_id = ms.mimat_id
    )
),

hard_pick as (
    select gene_id, transcript_id, mimat_id
    from (
        select
            *,
            row_number() over (partition by gene_id order by u_hard, mimat_id) as rk
        from candidates
        where has_site
    ) as h
    where rk <= n_hard_target
),

remaining as (
    select
        g.gene_id,
        g.n_total - coalesce(h.n_hard, 0)                    as n_left
    from genes as g
    left join (select gene_id, count(*) as n_hard from hard_pick group by gene_id) as h
        on h.gene_id = g.gene_id
),

rest as (
    select
        c.*,
        cast(ceil(r.n_left / 2.0) as bigint)                 as n_weighted,
        r.n_left - cast(ceil(r.n_left / 2.0) as bigint)      as n_random
    from candidates as c
    inner join remaining as r
        on r.gene_id = c.gene_id
    where not exists (
        select 1 from hard_pick as h
        where h.gene_id = c.gene_id and h.mimat_id = c.mimat_id
    )
),

weighted_pick as (
    select gene_id, transcript_id, mimat_id
    from (
        select
            *,
            row_number() over (
                partition by gene_id
                order by pow(u_weighted, 1.0 / mir_degree) desc, mimat_id
            ) as rk
        from rest
    ) as w
    where rk <= n_weighted
),

random_pick as (
    select gene_id, transcript_id, mimat_id
    from (
        select
            *,
            row_number() over (partition by gene_id order by u_random, mimat_id) as rk
        from rest as x
        where not exists (
            select 1 from weighted_pick as w
            where w.gene_id = x.gene_id and w.mimat_id = x.mimat_id
        )
    ) as z
    where rk <= n_random
)

select gene_id, transcript_id, mimat_id, 0 as label, 'seed_matched' as pair_type from hard_pick
union all
select gene_id, transcript_id, mimat_id, 0 as label, 'degree_matched' as pair_type from weighted_pick
union all
select gene_id, transcript_id, mimat_id, 0 as label, 'random' as pair_type from random_pick
