-- Fails if a held-out miRNA appears in train or val (would contaminate cold_both).
select pair_id
from {{ ref('fct_pairs') }}
where mirna_holdout and split in ('train', 'val')
