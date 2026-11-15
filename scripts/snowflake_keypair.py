"""Generate an RSA key pair for Snowflake key-pair authentication.

Snowflake finished deprecating single-factor password login in October 2026: human users must
pass MFA on every password sign-in (which would mean an MFA push per dbt connection), and SERVICE
users cannot hold a password at all. So programmatic access goes through a key pair.

The private key is written OUTSIDE the repository, to %USERPROFILE%\\.snowflake\\ by default, and
the script prints the ALTER USER statement to paste into Snowsight.

Usage:
    uv run python scripts/snowflake_keypair.py
    uv run python scripts/snowflake_keypair.py --passphrase-env SNOWFLAKE_PRIVATE_KEY_PASSPHRASE
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import os
import stat
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def fingerprint_of(private_path: Path, passphrase: bytes | None) -> tuple[str, str]:
    """Snowflake's RSA_PUBLIC_KEY_FP: base64 SHA-256 of the DER public key, 'SHA256:' prefixed.

    Returns (fingerprint, public key body) so a mismatch can be fixed in the same step.
    """
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=passphrase)
    der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = base64.b64encode(hashlib.sha256(der).digest()).decode()
    body = base64.b64encode(der).decode()
    return f"SHA256:{digest}", body


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path.home() / ".snowflake",
        help="where to write the keys (default: ~/.snowflake, deliberately outside the repo)",
    )
    ap.add_argument("--name", default="spongescope")
    ap.add_argument(
        "--passphrase-env",
        default=None,
        help="name of an env var holding a passphrase; omit for an unencrypted key",
    )
    ap.add_argument("--user", default="SPONGESCOPE_SVC", help="Snowflake user for the ALTER stmt")
    ap.add_argument("--force", action="store_true", help="overwrite an existing key")
    ap.add_argument(
        "--fingerprint",
        action="store_true",
        help="print the fingerprint of the EXISTING key and the ALTER statement; generates nothing",
    )
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    private_path = args.out_dir / f"{args.name}_rsa_key.p8"
    public_path = args.out_dir / f"{args.name}_rsa_key.pub"

    if args.fingerprint:
        if not private_path.exists():
            sys.exit(f"no key at {private_path} -- run without --fingerprint to generate one")
        raw = os.environ.get(args.passphrase_env) if args.passphrase_env else None
        fp, body = fingerprint_of(private_path, raw.encode() if raw else None)
        print(f"private key: {private_path}")
        print(f"fingerprint: {fp}\n")
        print("Compare with Snowflake:\n")
        print(f"  desc user {args.user};        -- look at the RSA_PUBLIC_KEY_FP row")
        print("\nIf they differ, or the row is empty, run this:\n")
        print(f"alter user {args.user} set rsa_public_key='{body}';")
        return

    if private_path.exists() and not args.force:
        sys.exit(
            f"{private_path} already exists.\n"
            "Re-run with --force only if you intend to replace the key -- the old public key in "
            "Snowflake would then stop matching and every connection would fail until you paste "
            "the new one."
        )

    passphrase: bytes | None = None
    if args.passphrase_env:
        raw = os.environ.get(args.passphrase_env)
        if not raw:
            sys.exit(f"{args.passphrase_env} is not set")
        passphrase = raw.encode()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encryption = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path.write_bytes(public_pem)

    # Owner-only, as far as the platform allows. On Windows this is advisory: NTFS ACLs are what
    # actually protect the file, so keeping it under your user profile is the real control.
    with contextlib.suppress(OSError):
        private_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    body = "".join(
        line for line in public_pem.decode().splitlines() if not line.startswith("-----")
    )

    print(f"private key: {private_path}")
    print(f"public key:  {public_path}")
    if passphrase:
        print(f"encrypted with the value of {args.passphrase_env}")
    else:
        print("unencrypted (no passphrase) -- fine for a laptop-local trial key, but it is a")
        print("long-lived secret with no expiry, so keep it out of the repo and out of backups")

    print("\nPaste this into a Snowsight worksheet:\n")
    print(f"alter user {args.user} set rsa_public_key='{body}';")

    print("\nThen set, for this shell:\n")
    print(f'  $env:SNOWFLAKE_PRIVATE_KEY_PATH = "{private_path}"')
    if passphrase:
        print(f'  $env:{args.passphrase_env} = "<the passphrase>"')


if __name__ == "__main__":
    main()
