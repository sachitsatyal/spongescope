-- One row per lncRNA gene with its MMseqs2 cluster (cluster_id = representative gene ID).
select
    gene_id,
    cluster_rep as cluster_id
from {{ source('raw', 'lnc_clusters') }}
