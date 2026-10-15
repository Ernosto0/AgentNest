"""Command line: ``python -m app.cli <command>``.

Commands: ``seed [--reset]``, ``create-user``, ``generate-key``, ``export-openapi``.
Machine-readable output goes to stdout; logs go to stderr.
"""

import argparse
import getpass
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.clock import SystemClock
from app.core.config import ConfigError, get_settings
from app.core.db import get_session_factory
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.security import generate_encryption_key, generate_secret_key
from app.demo.seed import SeedError, seed
from app.identity import service
from app.main import create_app


def cmd_seed(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        report = seed(get_session_factory(), SystemClock(), settings, reset=args.reset)
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.reset:
        print(
            f"Reset: removed {report.removed_workspaces} workspaces, {report.removed_users} users."
        )
    print(
        f"Users:       {len(report.created_users)} created, {len(report.existing_users)} existing"
    )
    print(
        f"Workspaces:  {len(report.created_workspaces)} created, "
        f"{len(report.existing_workspaces)} existing"
    )
    print("Log in as owner@demo.local / manager@demo.local / staff@demo.local / other@demo.local")
    print("with the value of DEMO_PASSWORD.")
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password: ")
    session_factory = get_session_factory()
    try:
        with session_factory() as session:
            user = service.create_user(
                session,
                email=args.email,
                password=password,
                display_name=args.display_name,
                ui_locale=args.locale,
            )
    except AppError as exc:
        detail = (
            "; ".join(f"{e['field']}: {e['code']}" for e in exc.params.get("errors", []))
            or exc.code
        )
        print(f"error: {detail}", file=sys.stderr)
        return 1
    print(f"Created user {user.email} ({user.id})")
    return 0


def cmd_generate_key(args: argparse.Namespace) -> int:
    print(generate_secret_key() if args.kind == "secret" else generate_encryption_key(args.key_id))
    return 0


def cmd_export_openapi(args: argparse.Namespace) -> int:
    # Quiet app startup: logs are not wanted in a generated artefact.
    settings = get_settings().model_copy(update={"log_level": "ERROR"})
    spec = create_app(settings).openapi()
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        # newline="" keeps LF on Windows; explicit UTF-8 avoids PowerShell's UTF-16 redirects.
        with Path(args.output).open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="AgentNest commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="create demo users and workspaces (never in production)")
    p_seed.add_argument("--reset", action="store_true", help="remove seeded data first")
    p_seed.set_defaults(func=cmd_seed)

    p_user = sub.add_parser("create-user", help="create a user")
    p_user.add_argument("--email", required=True)
    p_user.add_argument("--display-name", required=True)
    p_user.add_argument("--locale", choices=("tr", "en"), default="tr")
    p_user.add_argument("--password", help="omit to be prompted (keeps it out of shell history)")
    p_user.set_defaults(func=cmd_create_user)

    p_key = sub.add_parser("generate-key", help="print a new random key")
    p_key.add_argument(
        "--kind",
        choices=("secret", "token-encryption"),
        default="secret",
        help="secret: a SECRET_KEY value; token-encryption: a TOKEN_ENCRYPTION_KEYS entry",
    )
    p_key.add_argument("--key-id", default="k1", help="key id for --kind token-encryption")
    p_key.set_defaults(func=cmd_generate_key)

    p_api = sub.add_parser("export-openapi", help="print the OpenAPI document as JSON")
    p_api.add_argument("-o", "--output", help="write UTF-8 to this file instead of stdout")
    p_api.set_defaults(func=cmd_export_openapi)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    configure_logging(settings)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
