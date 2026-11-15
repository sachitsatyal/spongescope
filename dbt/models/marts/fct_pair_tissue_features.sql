-- Expression-context features for every pair in fct_pairs.
--
-- Both sides are aggregated to atlas organ_system (via the tissue_map seed), then compared:
--   coexpr       Pearson correlation of the two organ-level profiles; NULL below 3 shared
--                organs, since a correlation over 1-2 points is not a measurement
--   max_cooccur  best single organ for the pair: max over organs of min(lnc_frac, mir_frac),
--                where each side is scaled by its own maximum, so this is "is there an organ
--                where BOTH are near their peak?"
-- Pairs whose miRNA is absent from the atlas get nulls and mirna_atlas_known = false; the model
-- must see that flag rather than treat a missing value as zero.
-- NOTE: fct_pairs.cell_contexts is label-derived (positives only) and must never be a feature.
with organ_map as (
    select gtex_tissue, atlas_organ_system
    from {{ ref('tissue_map') }}
    where atlas_organ_system is not null and atlas_organ_system <> ''
),

lnc_organ as (
    select
        e.gene_id,
        m.atlas_organ_system as organ,
        avg(e.log1p_tpm)     as lnc_level
    from {{ ref('fct_lncrna_tissue_expression') }} as e
    inner join organ_map as m
        on m.gtex_tissue = e.tissue
    group by e.gene_id, m.atlas_organ_system
),

mir_organ as (
    select
        mimat_id,
        organ_system          as organ,
        avg(log1p_mean_expr)  as mir_level
    from {{ ref('fct_mirna_tissue_expression') }}
    where biotype = 'tissue'
    group by mimat_id, organ_system
),

lnc_rel as (
    select
        gene_id,
        organ,
        lnc_level,
        lnc_level / nullif(max(lnc_level) over (partition by gene_id), 0) as lnc_frac
    from lnc_organ
),

mir_rel as (
    select
        mimat_id,
        organ,
        mir_level,
        mir_level / nullif(max(mir_level) over (partition by mimat_id), 0) as mir_frac
    from mir_organ
),

pair_organ as (
    select
        p.pair_id,
        l.organ,
        l.lnc_level,
        l.lnc_frac,
        r.mir_level,
        r.mir_frac,
        -- least() does NOT mean the same thing on both engines: DuckDB ignores NULL arguments
        -- and returns the smallest non-NULL one, Snowflake returns NULL if any argument is NULL.
        -- Unguarded, a lncRNA with no expression anywhere (lnc_frac NULL) silently scored its
        -- partner's mir_frac as co-occurrence on DuckDB. Snowflake's reading is the correct one
        -- for what this feature means, so the intent is now written out explicitly and both
        -- engines agree.
        case
            when l.lnc_frac is null or r.mir_frac is null then null
            else least(l.lnc_frac, r.mir_frac)
        end as cooccur
    from {{ ref('fct_pairs') }} as p
    inner join lnc_rel as l
        on l.gene_id = p.gene_id
    inner join mir_rel as r
        on  r.mimat_id = p.mimat_id
        and r.organ = l.organ
),

agg as (
    select
        pair_id,
        count(*)                                        as n_shared_organs,
        corr(lnc_level, mir_level)                      as coexpr_raw,
        max(cooccur)                                    as max_cooccur,
        avg(cooccur)                                    as mean_cooccur,
        max(lnc_level)                                  as lnc_max_level,
        max(mir_level)                                  as mir_max_level,
        avg(case when lnc_frac >= 0.5 then 1.0 else 0.0 end) as lnc_broad_frac,
        avg(case when mir_frac >= 0.5 then 1.0 else 0.0 end) as mir_broad_frac
    from pair_organ
    group by pair_id
)

select
    p.pair_id,
    a.pair_id is not null                       as mirna_atlas_known,
    coalesce(a.n_shared_organs, 0)              as n_shared_organs,
    -- corr() returns NaN (not NULL) when a pair shares too few organs or one side is flat
    -- across them. BETWEEN is false for NaN in both DuckDB and Snowflake, so this maps those
    -- cases to NULL -- which the GBM reads as missing instead of as a real correlation.
    case
        when a.n_shared_organs >= 3 and a.coexpr_raw between -1 and 1 then a.coexpr_raw
    end                                         as coexpr,
    a.max_cooccur,
    a.mean_cooccur,
    a.lnc_max_level,
    a.mir_max_level,
    a.lnc_broad_frac,
    a.mir_broad_frac,
    t.n_expressed_tissues                       as lnc_n_expressed_tissues,
    t.tau                                       as lnc_tau
from {{ ref('fct_pairs') }} as p
left join agg as a
    on a.pair_id = p.pair_id
left join {{ ref('dim_lncrna_tissue_profile') }} as t
    on t.gene_id = p.gene_id
