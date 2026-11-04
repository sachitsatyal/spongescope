-- Fails if any (gene, miRNA) positive appears more than once.
select gene_id, mimat_id, count(*) as n
from {{ ref('int_positive_pairs') }}
group by gene_id, mimat_id
having count(*) > 1
