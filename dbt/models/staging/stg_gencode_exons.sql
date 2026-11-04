-- Exon coordinates for lncRNA transcripts on main chromosomes only.
select
    split_part(transcript_id, '.', 1) as transcript_id,
    split_part(gene_id, '.', 1)       as gene_id,
    chrom,
    "start"                           as exon_start,
    "end"                             as exon_end,
    strand,
    exon_number
from {{ source('raw', 'gencode_lncrna_exons') }}
where transcript_id not like '%PAR_Y%'
  and chrom in (
    'chr1','chr2','chr3','chr4','chr5','chr6','chr7','chr8','chr9','chr10','chr11','chr12',
    'chr13','chr14','chr15','chr16','chr17','chr18','chr19','chr20','chr21','chr22','chrX','chrY'
  )
