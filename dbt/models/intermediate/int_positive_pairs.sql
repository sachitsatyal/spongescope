-- Positive (lncRNA gene, miRNA) pairs from ENCORI CLIP sites.
-- Inner joins drop retired gene IDs, genes with no eligible transcript (length cap),
-- and the ~0.5% of miRNAs missing from miRBase.
with sites as (
    select distinct
        site_id, gene_id, mimat_id, clip_exp_num, degradome_exp_num, site_type, cell_contexts
    from {{ ref('int_site_transcript_hits') }}
),

rep as (
    select gene_id, transcript_id
    from {{ ref('int_gene_representative') }}
),

on_rep as (
    select distinct h.site_id
    from {{ ref('int_site_transcript_hits') }} as h
    inner join rep as r
        on r.transcript_id = h.transcript_id
),

site_agg as (
    select
        s.gene_id,
        s.mimat_id,
        count(*)                                 as n_sites,
        count(o.site_id)                         as n_sites_on_transcript,
        max(s.clip_exp_num)                      as max_clip_exp_num,
        max(s.degradome_exp_num)                 as max_degradome_exp_num,
        string_agg(distinct s.site_type, ',')    as site_types
    from sites as s
    left join on_rep as o
        on o.site_id = s.site_id
    group by s.gene_id, s.mimat_id
),

contexts_long as (
    select
        gene_id,
        mimat_id,
        trim(unnest(string_split(cell_contexts, ','))) as cell_context
    from sites
    where cell_contexts is not null
),

ctx_agg as (
    select
        gene_id,
        mimat_id,
        count(distinct cell_context)              as n_cell_contexts,
        string_agg(distinct cell_context, ',')    as cell_contexts
    from contexts_long
    where cell_context <> ''
    group by gene_id, mimat_id
)

select
    r.gene_id,
    r.transcript_id,
    a.mimat_id,
    1                                   as label,
    'clip_positive'                     as pair_type,
    a.n_sites,
    a.n_sites_on_transcript,
    a.max_clip_exp_num,
    a.max_degradome_exp_num,
    a.site_types,
    coalesce(c.n_cell_contexts, 0)      as n_cell_contexts,
    c.cell_contexts
from site_agg as a
inner join rep as r
    on r.gene_id = a.gene_id
inner join {{ ref('stg_mirna') }} as m
    on m.mimat_id = a.mimat_id
left join ctx_agg as c
    on c.gene_id = a.gene_id
   and c.mimat_id = a.mimat_id
