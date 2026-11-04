-- Eligible lncRNA transcripts: on a main chromosome, 200 nt <= length <= max_lncrna_length.
with tx_locus as (
    select
        transcript_id,
        min(chrom)  as chrom,
        min(strand) as strand
    from {{ ref('stg_gencode_exons') }}
    group by transcript_id
)

select
    t.transcript_id,
    t.gene_id,
    t.gene_name,
    t.transcript_name,
    t.transcript_length,
    l.chrom,
    l.strand,
    t.sequence
from {{ ref('stg_lncrna_transcripts') }} as t
inner join tx_locus as l
    on l.transcript_id = t.transcript_id
where t.transcript_length between 200 and {{ var('max_lncrna_length') }}
