-- Fails if a negative pair has CLIP evidence.
select n.gene_id, n.mimat_id
from {{ ref('int_negative_pairs') }} as n
inner join {{ ref('int_positive_pairs') }} as p
    on p.gene_id = n.gene_id
   and p.mimat_id = n.mimat_id
