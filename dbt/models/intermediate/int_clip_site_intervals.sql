-- CLIP peak positions converted from genomic to transcript coordinates.
--
-- GENCODE numbers exons from the 5' end of the transcript, so exon_number is transcript order
-- on both strands. For a genomic position g inside exon e, the 0-based transcript offset is
--   '+' strand:  cum_before(e) + (g - exon_start)
--   '-' strand:  cum_before(e) + (exon_end - g)
-- A site's two ends swap order on the minus strand, hence least()/greatest().
-- Sites with an end outside every exon of the transcript (intronic) are dropped by the joins.
with exons as (
    select
        transcript_id,
        exon_start,
        exon_end,
        exon_number,
        coalesce(
            sum(exon_end - exon_start + 1) over (
                partition by transcript_id
                order by exon_number
                rows between unbounded preceding and 1 preceding
            ),
            0
        ) as cum_before
    from {{ ref('stg_gencode_exons') }}
),

sites as (
    select
        site_id,
        transcript_id,
        gene_id,
        mimat_id,
        strand,
        site_start,
        site_end,
        clip_exp_num,
        site_type
    from {{ ref('int_site_transcript_hits') }}
    where transcript_id is not null
),

mapped as (
    select
        s.site_id,
        s.transcript_id,
        s.gene_id,
        s.mimat_id,
        s.clip_exp_num,
        s.site_type,
        case
            when s.strand = '+' then es.cum_before + (s.site_start - es.exon_start)
            else es.cum_before + (es.exon_end - s.site_start)
        end as pos_a,
        case
            when s.strand = '+' then ee.cum_before + (s.site_end - ee.exon_start)
            else ee.cum_before + (ee.exon_end - s.site_end)
        end as pos_b
    from sites as s
    inner join exons as es
        on  es.transcript_id = s.transcript_id
        and s.site_start between es.exon_start and es.exon_end
    inner join exons as ee
        on  ee.transcript_id = s.transcript_id
        and s.site_end between ee.exon_start and ee.exon_end
)

select
    site_id,
    transcript_id,
    gene_id,
    mimat_id,
    clip_exp_num,
    site_type,
    least(pos_a, pos_b)    as tx_start,
    greatest(pos_a, pos_b) as tx_end
from mapped
