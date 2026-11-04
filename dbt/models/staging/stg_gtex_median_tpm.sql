-- GTEx v10 median TPM per gene per tissue (long format).
select
    gene_id,
    gene_name,
    tissue,
    median_tpm
from {{ source('raw', 'gtex_median_tpm') }}
