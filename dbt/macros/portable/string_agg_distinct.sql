{% macro string_agg_distinct(col, delim=',') -%}
    {{ return(adapter.dispatch('string_agg_distinct', 'spongescope')(col, delim)) }}
{%- endmacro %}

{% macro default__string_agg_distinct(col, delim) -%}
    string_agg(distinct {{ col }}, '{{ delim }}')
{%- endmacro %}

{% macro snowflake__string_agg_distinct(col, delim) -%}
    listagg(distinct {{ col }}, '{{ delim }}')
{%- endmacro %}
