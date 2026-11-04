-- Each ENCORI binding site (genomic coords) matched to every transcript of its gene
-- whose exons overlap the site. Sites with no matching exon keep transcript_id = null.
with sites as (
    select
        row_number() over (
            order by gene_id, mimat_id, chrom, site_start, site_end, strand
        ) as site_id,
        *
    from {{ ref('stg_encori_sites') }}
),

hits as (
    select distinct
        s.site_id,
        e.transcript_id
    from sites as s
    inner join {{ ref('stg_gencode_exons') }} as e
        on  e.gene_id = s.gene_id
        and e.chrom = s.chrom
        and e.strand = s.strand
        and s.site_start <= e.exon_end
        and s.site_end >= e.exon_start
)

select
    s.site_id,
    s.gene_id,
    s.mimat_id,
    s.chrom,
    s.site_start,
    s.site_end,
    s.strand,
    s.clip_exp_num,
    s.degradome_exp_num,
    s.site_type,
    s.cell_contexts,
    h.transcript_id
from sites as s
left join hits as h
    on h.site_id = s.site_id
