-- miRNAs used in fct_pairs: name, seed, hold-out flag, sequence.
select
    m.mimat_id,
    m.mirna_name,
    m.mirna_length,
    h.seed,
    h.is_holdout,
    m.sequence
from {{ ref('stg_mirna') }} as m
inner join {{ ref('int_mirna_holdout') }} as h
    on h.mimat_id = m.mimat_id
where m.mimat_id in (select distinct mimat_id from {{ ref('fct_pairs') }})
