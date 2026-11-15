{# Explode a comma-separated column into one row per value.

   This is the one construct where the two engines differ in *shape*, not just in function names.
   DuckDB unnests in the select list; Snowflake has no select-position unnest, so the array has to
   be flattened as a lateral join. That means two call sites, not one:

       select
           pair_key,
           {{ csv_explode_value('cell_contexts') }} as cell_context
       from some_cte
       {{ csv_explode_join('cell_contexts') }}

   On DuckDB the join expands to nothing and the value expression does the work; on Snowflake the
   join produces the rows and the value expression just reads the flattened column. #}
{% macro csv_explode_value(col, delim=',') -%}
    {{ return(adapter.dispatch('csv_explode_value', 'spongescope')(col, delim)) }}
{%- endmacro %}

{% macro default__csv_explode_value(col, delim) -%}
    trim(unnest(string_split({{ col }}, '{{ delim }}')))
{%- endmacro %}

{% macro snowflake__csv_explode_value(col, delim) -%}
    trim(_exploded.value::string)
{%- endmacro %}

{% macro csv_explode_join(col, delim=',') -%}
    {{ return(adapter.dispatch('csv_explode_join', 'spongescope')(col, delim)) }}
{%- endmacro %}

{% macro default__csv_explode_join(col, delim) -%}
{%- endmacro %}

{% macro snowflake__csv_explode_join(col, delim) -%}
    , lateral flatten(input => split({{ col }}, '{{ delim }}')) as _exploded
{%- endmacro %}
