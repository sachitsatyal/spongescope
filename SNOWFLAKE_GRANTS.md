# Grants the service role needs

Run once, as `ACCOUNTADMIN`, in a Snowsight worksheet:

```sql
use role accountadmin;

grant all on database SPONGESCOPE to role SPONGESCOPE_ROLE;
grant all on schema SPONGESCOPE.PUBLIC to role SPONGESCOPE_ROLE;
grant all on future schemas in database SPONGESCOPE to role SPONGESCOPE_ROLE;
grant usage, operate on warehouse SPONGESCOPE_WH to role SPONGESCOPE_ROLE;
```

## Why each line

`grant all on database` — the role needs to create `RAW`, `STAGING`, `INTERMEDIATE` and `MARTS`
inside it. The original setup granted `usage, create schema`, which turned out not to be enough
once dbt also wanted to describe and drop objects there.

`grant all on schema PUBLIC` — the `tissue_map` seed has no custom schema, so dbt falls back to
`target.schema`, which the profile sets to `PUBLIC`. That schema is created with the database and
owned by `ACCOUNTADMIN`, so the role had nothing on it and dbt failed before building anything.
(In dev the same fallback is why the seed loads as `main.tissue_map`.)

`grant all on future schemas` — schemas the role creates itself it already owns; this covers
anything created later by another role, so the grant doesn't have to be re-run.

`grant usage, operate on warehouse` — `usage` to run queries, `operate` to resume the warehouse
after its 60-second auto-suspend. Without `operate`, the first query after an idle minute fails.

## What the role deliberately does NOT get

No `CREATE WAREHOUSE` and no `CREATE DATABASE` on the account. A service identity that can create
account-level objects is a service identity that can run up a bill or stand up infrastructure
nobody is watching. The loader has been changed to match: it no longer issues any account-level
DDL, it only `use`s what the admin created, and it creates the `RAW` schema, which it owns.

That is also what the first error was telling you — `create warehouse if not exists` still
requires the privilege even when the warehouse already exists, so "if not exists" was never going
to get around it.
