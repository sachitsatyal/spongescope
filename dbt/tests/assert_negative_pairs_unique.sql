-- Fails if any (gene, miRNA) negative is sampled twice.
select gene_id, mimat_id, count(*) as n
from {{ ref('int_negative_pairs') }}
group by gene_id, mimat_id
having count(*) > 1
