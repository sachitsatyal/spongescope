-- Human mature miRNAs; MIMAT accession is the join key everywhere.
select
    mimat_id,
    mirna_name,
    length   as mirna_length,
    sequence
from {{ source('raw', 'mirna_mature') }}
