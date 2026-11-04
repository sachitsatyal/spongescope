-- One row per lncRNA transcript; version suffixes stripped, PAR_Y duplicates removed.
select
    split_part(transcript_id, '.', 1) as transcript_id,
    transcript_id                     as transcript_id_versioned,
    split_part(gene_id, '.', 1)       as gene_id,
    gene_name,
    transcript_name,
    length                            as transcript_length,
    sequence
from {{ source('raw', 'lncrna_transcripts') }}
where transcript_id not like '%PAR_Y%'
