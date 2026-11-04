-- Fails if a (gene, tissue) pair appears twice.
select gene_id, tissue, count(*) as n
from {{ ref('fct_lncrna_tissue_expression') }}
group by gene_id, tissue
having count(*) > 1
