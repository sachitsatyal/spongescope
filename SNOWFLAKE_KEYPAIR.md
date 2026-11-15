# Snowflake access: key pair, not password

Snowflake finished deprecating single-factor password login in October 2026. Your account was
created after that, so:

- a **human** user can still use a password, but only with MFA — which means an MFA push on every
  dbt connection and every loader run. Unusable for automation.
- a **SERVICE** user cannot hold a password at all. Key pair, OAuth, or a programmatic access
  token.

So the project authenticates with a key pair against a dedicated service user. That's also the
right shape for Phase 7, where CI needs to connect without a human present.

## 1. Create the warehouse, database, role and service user

In a Snowsight worksheet, as `ACCOUNTADMIN`:

```sql
use role accountadmin;

create warehouse if not exists SPONGESCOPE_WH
  warehouse_size = xsmall
  auto_suspend = 60
  auto_resume = true
  initially_suspended = true;

create database if not exists SPONGESCOPE;
create role if not exists SPONGESCOPE_ROLE;

grant usage, operate on warehouse SPONGESCOPE_WH to role SPONGESCOPE_ROLE;
grant usage, create schema on database SPONGESCOPE to role SPONGESCOPE_ROLE;
grant role SPONGESCOPE_ROLE to role accountadmin;   -- so you can see what it creates

create user if not exists SPONGESCOPE_SVC
  type = service
  default_role = SPONGESCOPE_ROLE
  default_warehouse = SPONGESCOPE_WH
  comment = 'SpongeScope loader + dbt';

grant role SPONGESCOPE_ROLE to user SPONGESCOPE_SVC;
```

`type = service` is the important word: it makes a password impossible on this user, so the
account can't be reduced to a single secret someone phishes.

## 2. Generate the key pair

```powershell
cd $HOME\projects\spongescope
uv run python scripts\snowflake_keypair.py
```

Writes the private key to `%USERPROFILE%\.snowflake\spongescope_rsa_key.p8` — **outside the
repo**, deliberately — and prints a ready-to-paste `alter user ... set rsa_public_key='...'`
statement. Run that statement in Snowsight.

For an encrypted key instead:

```powershell
$env:SNOWFLAKE_PRIVATE_KEY_PASSPHRASE = "<something long>"
uv run python scripts\snowflake_keypair.py --passphrase-env SNOWFLAKE_PRIVATE_KEY_PASSPHRASE
```

An unencrypted key is reasonable for a 30-day trial on your own laptop. It is still a long-lived
secret with no expiry, so it stays out of the repo and out of any backup that leaves the machine.

## 3. Set the environment

```powershell
$env:SNOWFLAKE_ACCOUNT          = "JFFJFPB-OI42672"
$env:SNOWFLAKE_USER             = "SPONGESCOPE_SVC"
$env:SNOWFLAKE_PRIVATE_KEY_PATH = "$HOME\.snowflake\spongescope_rsa_key.p8"
$env:SNOWFLAKE_ROLE             = "SPONGESCOPE_ROLE"
$env:SNOWFLAKE_WAREHOUSE        = "SPONGESCOPE_WH"
$env:SNOWFLAKE_DATABASE         = "SPONGESCOPE"
```

Note `SNOWFLAKE_USER` is now the **service user**, not your own login. There is no
`SNOWFLAKE_PASSWORD` any more — the replacement `profiles.yml` in this zip uses
`private_key_path`, and the loader and `compare_targets.py` read the same key.

## 4. Verify, then run

```powershell
cd dbt ; uv run dbt debug --target prod --profiles-dir . ; cd ..

uv run python -m spongescope.data.load_snowflake --dry-run
uv run python -m spongescope.data.load_snowflake
cd dbt ; uv run dbt build --target prod --profiles-dir . ; cd ..
uv run python scripts\compare_targets.py
```

`dbt debug` should report `Connection test: OK`. Failure modes worth telling apart:

| Message | Cause |
|---|---|
| `404 Not Found` | account identifier wrong, not credentials |
| `JWT token is invalid` | public key in Snowflake doesn't match the private key on disk — re-run the `alter user` statement |
| `Role 'SPONGESCOPE_ROLE' specified ... not granted` | step 1 didn't run, or ran under a different role |
| MFA prompt | you're still connecting as your human user; `SNOWFLAKE_USER` should be `SPONGESCOPE_SVC` |

## Replacing your own login later

If you ever need a second key (CI, another machine), add it as a *second* key rather than
replacing the first: `alter user SPONGESCOPE_SVC set rsa_public_key_2='...'`. Snowflake accepts
either, which is how you rotate without a window where nothing can connect.
