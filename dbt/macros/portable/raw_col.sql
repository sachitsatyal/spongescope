{# A raw column as each warehouse spells it.

   The ENCORI and atlas downloads have mixed-case and punctuated column names ("miRNAid",
   "cellline/tissue"). DuckDB keeps them verbatim, so the models quote them. The Snowflake loader
   normalizes every name to lower-case snake_case and writes it unquoted, so Snowflake stores it
   upper case and binds without quotes.

   {{ raw_col('miRNAid') }}         -> "miRNAid"        on DuckDB, "MIRNAID"         on Snowflake
   {{ raw_col('cellline/tissue') }} -> "cellline/tissue"              "CELLLINE_TISSUE"
   {{ raw_col('start') }}           -> "start"                        "START"

   The Snowflake side is quoted UPPER CASE, not bare lower case, because several raw columns are
   reserved words (ENCORI has `start` and `end`) and a bare reserved word is a syntax error.
   Upper case is what Snowflake stores for an unquoted name anyway, so quoting costs nothing.

   normalize_ident must stay in step with normalize() in load_snowflake.py. #}
{% macro normalize_ident(name) -%}
    {%- set lowered = name | lower -%}
    {%- set parts = [] -%}
    {%- for char in lowered -%}
        {%- if char.isalnum() -%}
            {%- do parts.append(char) -%}
        {%- else -%}
            {%- do parts.append('_') -%}
        {%- endif -%}
    {%- endfor -%}
    {%- set joined = parts | join('') -%}
    {%- set collapsed = joined.split('_') | reject('equalto', '') | join('_') -%}
    {{ return(collapsed) }}
{%- endmacro %}

{% macro raw_col(name) -%}
    {{ return(adapter.dispatch('raw_col', 'spongescope')(name)) }}
{%- endmacro %}

{% macro default__raw_col(name) -%}
    "{{ name }}"
{%- endmacro %}

{% macro snowflake__raw_col(name) -%}
    "{{ normalize_ident(name) | upper }}"
{%- endmacro %}
