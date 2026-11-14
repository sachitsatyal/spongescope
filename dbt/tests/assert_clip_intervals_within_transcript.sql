-- Fails if a mapped CLIP interval lands outside its transcript, which would mean the
-- genomic -> transcript arithmetic is wrong.
select
    i.site_id,
    i.transcript_id,
    i.tx_start,
    i.tx_end,
    t.transcript_length
from {{ ref('int_clip_site_intervals') }} as i
inner join {{ ref('int_lncrna_transcripts') }} as t
    on t.transcript_id = i.transcript_id
where i.tx_start < 0 or i.tx_end >= t.transcript_length
