{# The miRNA tissue atlas is the one place the two warehouses genuinely diverge rather than
   just needing different syntax.

   On DuckDB the raw table is wide (674 rows x 2,660 miRNA columns) and `UNPIVOT ... columns(*
   exclude (...))` reshapes it in SQL. Snowflake's UNPIVOT needs an explicit column list, and
   writing out 2,656 column names is not a macro -- it is a generated file that would break
   whenever the atlas is re-released. So on Snowflake the loader reshapes it in pandas and writes
   an already-long table, and this macro picks whichever source applies.

   Consequence to keep in mind: on Snowflake `stg_mirna_tissue_atlas` is a thin passthrough, so
   the reshaping logic is covered by the loader's tests, not by dbt tests. #}
{% macro atlas_is_prereshaped() -%}
    {{ return(target.type == 'snowflake') }}
{%- endmacro %}
