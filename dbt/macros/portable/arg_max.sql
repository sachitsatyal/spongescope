{# Value of `value_col` in the row where `order_col` is largest. #}
{% macro arg_max(value_col, order_col) -%}
    {{ return(adapter.dispatch('arg_max', 'spongescope')(value_col, order_col)) }}
{%- endmacro %}

{% macro default__arg_max(value_col, order_col) -%}
    arg_max({{ value_col }}, {{ order_col }})
{%- endmacro %}

{% macro snowflake__arg_max(value_col, order_col) -%}
    max_by({{ value_col }}, {{ order_col }})
{%- endmacro %}
