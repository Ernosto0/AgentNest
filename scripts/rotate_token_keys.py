#!/usr/bin/env python3
"""Administrative CLI script for token encryption key rotation (Phase 8 Session 12, P8-06).

Usage:
    python scripts/rotate_token_keys.py [--batch-size 100]

Scans social_accounts where token_key_id != TOKEN_ENCRYPTION_ACTIVE_KEY_ID,
re-encrypts tokens in-place preserving AAD, and logs immutable security audit events.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.operations.key_rotation import rotate_social_account_tokens


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-encrypt social account tokens with active encryption key."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of accounts to scan and rotate per batch (default: 100)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.token_encryption_active_key_id:
        print("ERROR: TOKEN_ENCRYPTION_ACTIVE_KEY_ID is not configured.", file=sys.stderr)
        return 1

    print(
        f"Starting token key rotation to active key ID: '{settings.token_encryption_active_key_id}'..."
    )
    factory = get_session_factory()
    clock = SystemClock()

    result = rotate_social_account_tokens(
        factory, settings, clock, batch_size=args.batch_size
    )

    print("\n--- Token Key Rotation Summary ---")
    print(f"Active Key ID: {result.active_key_id}")
    print(f"Scanned:       {result.scanned}")
    print(f"Rotated:       {result.rotated}")
    print(f"Skipped:       {result.skipped}")
    print(f"Failed:        {result.failed}")

    if result.failed > 0:
        print(f"\nWARNING: {result.failed} account(s) failed key rotation. Inspect audit logs.", file=sys.stderr)
        return 1

    print("\nRotation completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

