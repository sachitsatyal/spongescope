-- Map our miRBase mature names to miRNATissueAtlas column names.
--
-- 529/638 match exactly. Most of the rest are miRNAs with a single annotated arm, where the
-- atlas uses the older un-suffixed name (hsa-miR-107 for our hsa-miR-107-3p). Stripping the arm
-- is only safe when the atlas has the stem and NEITHER arm variant -- otherwise the stem is
-- ambiguous and -5p/-3p are different molecules, so we leave it unmatched.
with atlas as (
    select distinct mirna_name from {{ ref('stg_mirna_tissue_atlas') }}
),

mir as (
    select mimat_id, mirna_name from {{ ref('dim_mirna') }}
),

exact as (
    select
        m.mimat_id,
        m.mirna_name,
        a.mirna_name as atlas_name,
        'exact' as match_type
    from mir as m
    inner join atlas as a
        on a.mirna_name = m.mirna_name
),

stemmed as (
    select
        m.mimat_id,
        m.mirna_name,
        case
            when right(m.mirna_name, 3) in ('-5p', '-3p')
                then left(m.mirna_name, length(m.mirna_name) - 3)
        end as stem
    from mir as m
    where not exists (select 1 from exact as e where e.mimat_id = m.mimat_id)
),

by_stem as (
    select
        s.mimat_id,
        s.mirna_name,
        a.mirna_name as atlas_name,
        'arm_stripped' as match_type
    from stemmed as s
    inner join atlas as a
        on a.mirna_name = s.stem
    where s.stem is not null
      and not exists (select 1 from atlas as x where x.mirna_name = s.stem || '-5p')
      and not exists (select 1 from atlas as x where x.mirna_name = s.stem || '-3p')
)

select * from exact
union all
select * from by_stem
