-- One row per CLIP-supported miRNA binding site on a lncRNA gene (genomic coordinates).
select
    "miRNAid"          as mimat_id,
    "miRNAname"        as mirna_name_encori,
    "geneID"           as gene_id,
    "geneName"         as gene_name,
    chromosome         as chrom,
    "start"            as site_start,
    "end"              as site_end,
    strand,
    "clipExpNum"       as clip_exp_num,
    "degraExpNum"      as degradome_exp_num,
    "RBP"              as ago_proteins,
    "merClass"         as site_type,
    "TDMDScore"        as tdmd_score,
    "phyloP"           as phylop,
    "pancancerNum"     as pancancer_num,
    "cellline/tissue"  as cell_contexts
from {{ source('raw', 'encori_mirna_lncrna') }}
