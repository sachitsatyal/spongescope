{#- Deterministic pseudo-random number in (0, 1) from a string expression + salt.
    Same inputs -> same number on every run, so negatives are reproducible. -#}
{% macro stable_uniform(expr, salt) -%}
    {%- if target.type == 'snowflake' -%}
        ((abs(hash({{ expr }} || '|{{ salt }}')) % 1000000) + 0.5) / 1000000.0
    {%- else -%}
        ((hash({{ expr }} || '|{{ salt }}') % 1000000) + 0.5) / 1000000.0
    {%- endif -%}
{%- endmacro %}
