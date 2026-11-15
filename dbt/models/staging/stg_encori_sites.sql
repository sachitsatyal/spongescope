-- One row per CLIP-supported miRNA binding site on a lncRNA gene (genomic coordinates).
select
    {{ raw_col('miRNAid') }}          as mimat_id,
    {{ raw_col('miRNAname') }}        as mirna_name_encori,
    {{ raw_col('geneID') }}           as gene_id,
    {{ raw_col('geneName') }}         as gene_name,
    chromosome         as chrom,
    {{ raw_col('start') }}            as site_start,
    {{ raw_col('end') }}              as site_end,
    strand,
    {{ raw_col('clipExpNum') }}       as clip_exp_num,
    {{ raw_col('degraExpNum') }}      as degradome_exp_num,
    {{ raw_col('RBP') }}              as ago_proteins,
    {{ raw_col('merClass') }}         as site_type,
    {{ raw_col('TDMDScore') }}        as tdmd_score,
    {{ raw_col('phyloP') }}           as phylop,
    {{ raw_col('pancancerNum') }}     as pancancer_num,
    {{ raw_col('cellline/tissue') }}  as cell_contexts
from {{ source('raw', 'encori_mirna_lncrna') }}
