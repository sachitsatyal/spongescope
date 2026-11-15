-- Every pair must get a feature row; coexpr must be a real correlation or NULL (never NaN).
select 'missing_rows' as problem, count(*) as n
from {{ ref('fct_pairs') }} as p
left join {{ ref('fct_pair_tissue_features') }} as f on f.pair_id = p.pair_id
where f.pair_id is null
having count(*) > 0

union all

-- NaN sorts above every number in DuckDB, so an out-of-range value here means a NaN leaked
-- through the guard in the model.
select 'coexpr_not_a_correlation' as problem, count(*) as n
from {{ ref('fct_pair_tissue_features') }}
where coexpr is not null and coexpr not between -1 and 1
having count(*) > 0

union all

-- A correlation over 1-2 points is not a measurement; the model must null those out.
select 'coexpr_with_too_few_organs' as problem, count(*) as n
from {{ ref('fct_pair_tissue_features') }}
where coexpr is not null and n_shared_organs < 3
having count(*) > 0
