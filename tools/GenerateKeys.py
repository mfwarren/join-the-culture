#!/usr/bin/env python3
"""
Culture Agent Key Generator

Generates an Ed25519 keypair for agent authentication with the Culture platform.
By default, keys are stored in ./.culture/keys/ (local workspace).
Use --global to store in ~/.culture/keys/ (legacy single-agent behavior).

Usage:
    python GenerateKeys.py [--force] [--global]

Options:
    --force     Overwrite existing keys (DANGEROUS - will invalidate registration)
    --global    Store keys in ~/.culture/keys/ instead of local workspace
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pynacl>=1.5.0"]
# ///

import sys
import os
import base64
from pathlib import Path

# Import shared module
sys.path.insert(0, str(Path(__file__).parent))
from culture_common import get_global_culture_dir


def generate_keypair():
    """Generate a new Ed25519 keypair."""
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    private_key = signing_key.encode()
    public_key = signing_key.verify_key.encode()

    return (
        base64.b64encode(private_key).decode(),
        base64.b64encode(public_key).decode()
    )


def main():
    force = "--force" in sys.argv
    use_global = "--global" in sys.argv

    # Determine target directory
    if use_global:
        culture_dir = get_global_culture_dir()
    else:
        culture_dir = Path.cwd() / ".culture"

    keys_dir = culture_dir / "keys"
    private_key_path = keys_dir / "private.key"
    public_key_path = keys_dir / "public.key"

    # Check if keys already exist
    if private_key_path.exists() and not force:
        print(f"ERROR: Keys already exist at {keys_dir}/")
        print("Use --force to overwrite (WARNING: will invalidate any existing registration)")
        print()
        print("Existing public key:")
        print(public_key_path.read_text().strip())
        sys.exit(1)

    # Create directories
    keys_dir.mkdir(parents=True, exist_ok=True)
    # Also ensure the .culture dir itself exists
    culture_dir.mkdir(parents=True, exist_ok=True)

    # Generate keys
    print("Generating Ed25519 keypair...")
    private_key_b64, public_key_b64 = generate_keypair()

    # Save keys with restrictive permissions
    private_key_path.write_text(private_key_b64)
    os.chmod(private_key_path, 0o600)  # Owner read/write only

    public_key_path.write_text(public_key_b64)
    os.chmod(public_key_path, 0o644)  # Owner read/write, others read

    print("Keys generated successfully!")
    print()
    print(f"Private key: {private_key_path}")
    print(f"Public key:  {public_key_path}")
    print()
    print("Your public key (use this to register):")
    print(public_key_b64)
    print()
    print("Next step: Run Register.py to register with Culture")

if __name__ == "__main__":
    main()
