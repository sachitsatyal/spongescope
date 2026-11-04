-- Hold out mirna_holdout_frac of miRNA seed families (nt 2-8) for a cold-both test set.
-- Whole seed families are held out, because miRNAs sharing a seed target the same sites.
with mirs as (
    select
        mimat_id,
        substr(sequence, 2, 7) as seed
    from {{ ref('stg_mirna') }}
),

families as (
    select
        seed,
        {{ stable_uniform("seed", var('seed') ~ '_mir') }} as u
    from (select distinct seed from mirs)
)

select
    m.mimat_id,
    m.seed,
    f.u < {{ var('mirna_holdout_frac') }} as is_holdout
from mirs as m
inner join families as f
    on f.seed = m.seed
