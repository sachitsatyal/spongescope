-- Fails if a lncRNA gene appears in more than one split (leakage).
select gene_id
from {{ ref('fct_pairs') }}
group by gene_id
having count(distinct lncrna_split) > 1
