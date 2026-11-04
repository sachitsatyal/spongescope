-- One representative transcript per lncRNA gene:
-- the eligible transcript carrying the most CLIP sites, then the longest, then by ID.
with site_counts as (
    select
        transcript_id,
        count(distinct site_id) as n_sites_on_transcript
    from {{ ref('int_site_transcript_hits') }}
    where transcript_id is not null
    group by transcript_id
),

ranked as (
    select
        t.gene_id,
        t.gene_name,
        t.transcript_id,
        t.transcript_length,
        t.chrom,
        t.strand,
        coalesce(sc.n_sites_on_transcript, 0) as n_sites_on_transcript,
        t.sequence,
        row_number() over (
            partition by t.gene_id
            order by coalesce(sc.n_sites_on_transcript, 0) desc,
                     t.transcript_length desc,
                     t.transcript_id
        ) as rk
    from {{ ref('int_lncrna_transcripts') }} as t
    left join site_counts as sc
        on sc.transcript_id = t.transcript_id
)

select
    gene_id,
    gene_name,
    transcript_id,
    transcript_length,
    chrom,
    strand,
    n_sites_on_transcript,
    sequence
from ranked
where rk = 1
