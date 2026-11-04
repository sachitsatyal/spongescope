-- Fails if a sequence cluster is spread across splits (near-duplicate leakage).
select cluster_id
from {{ ref('fct_pairs') }}
group by cluster_id
having count(distinct lncrna_split) > 1
