# Scanner rules corrected

The `bare reserved word` rule I added matched "reserved word followed by `as`", which is ordinary
SQL — `end as pos_a` (CASE), `cast(null as bigint)`, and `from {{ ref(...) }} as t` (the Jinja is
blanked before matching, leaving `from` beside the alias). All 22 hits were noise.

Worse, it **missed** the real problem. Only staging models read raw tables, and they reference
coordinate columns as `"start"` — quoted lowercase — which my lookbehind excluded. Quoted
lowercase is exactly what breaks now: the loader stores `"START"`, so `"start"` does not bind.

Two rules now, applied **only under `models/staging/`**, since nowhere else reads raw columns:

- `lowercase-quoted raw column` — `"start"`, `"gene_id"`: will not bind to the upper-case stored
  name.
- `bare reserved word as a column` — tightened to require the word to start a select-list item
  (line start or after a comma) and be followed by a comma or `as`.

The second can still flag a `CASE … END` if one ever appears in a staging model. It's scoped
tightly enough that a stray hit is cheap to dismiss, and I'd rather it over-report in one
directory than miss a real one.

```powershell
uv run python scripts\check_sql_portability.py
```
