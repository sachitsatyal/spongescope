-- lncRNAs used in fct_pairs: representative transcript, cluster, split, sequence.
select
    r.gene_id,
    r.gene_name,
    r.transcript_id,
    r.transcript_length,
    r.chrom,
    r.strand,
    s.cluster_id,
    s.cluster_size,
    s.lncrna_split,
    r.sequence
from {{ ref('int_gene_representative') }} as r
inner join {{ ref('int_lncrna_splits') }} as s
    on s.gene_id = r.gene_id
