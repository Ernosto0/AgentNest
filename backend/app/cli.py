"""Command line: ``python -m app.cli <command>``.

Commands: ``seed [--reset]``, ``create-user``, ``generate-key``, ``export-openapi``,
``simulate-message``, ``simulate-native-reply``, ``run-due-jobs`` (the developer simulator),
``check-config``, ``migration-status``, ``post-restore-reconcile``, and ``verify-db-roles``.
Machine-readable output goes to stdout; logs go to stderr.
"""

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.core.clock import Clock, SystemClock
from app.core.config import ConfigError, Settings, get_settings, validate_production_settings
from app.core.db import check_readiness, get_session_factory, migration_head, migration_revisions
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.security import generate_encryption_key, generate_secret_key
from app.demo import simulator
from app.demo.seed import SeedError, seed
from app.identity import repository as identity_repo
from app.identity import service
from app.integrations.channels.telegram import TelegramClient, process_update
from app.jobs.testing import run_due_jobs
from app.main import create_app
from app.operations.backup_restore import (
    TombstoneManifest,
    load_tombstone_manifest,
    post_restore_reconcile,
    provision_database_roles,
    verify_database_roles,
)


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
    for slug, added in report.seeded_facts.items():
        print(f"Facts:       {slug}: {added} added")
    for slug in report.connected_accounts:
        print(f"Instagram:   {slug}: simulated account connected")
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
    if args.kind == "secret":
        print(generate_secret_key())
        return 0
    default_id = "b1" if args.kind == "backup-encryption" else "k1"
    key_id = args.key_id or default_id
    print(generate_encryption_key(key_id))
    return 0


def cmd_export_openapi(args: argparse.Namespace) -> int:
    # Quiet app startup: logs are not wanted in a generated artefact.
    settings = get_settings().model_copy(
        update={
            "log_level": "ERROR",
            "demo_tools_enabled": True,
            "app_env": "development",
        }
    )
    spec = create_app(settings).openapi()
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        # newline="" keeps LF on Windows; explicit UTF-8 avoids PowerShell's UTF-16 redirects.
        with Path(args.output).open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


def _post_webhook(settings: Settings, prepared: simulator.PreparedWebhook) -> int:
    """Post a signed simulated webhook to the running API, like Instagram would."""
    url = f"{settings.app_base_url.rstrip('/')}/webhooks/instagram/mock"
    if not url.startswith(("http://", "https://")):
        print("error: APP_BASE_URL must be an http(s) URL", file=sys.stderr)
        return 1
    request = urllib.request.Request(  # noqa: S310  (scheme checked above)
        url,
        data=prepared.body,
        headers={"Content-Type": "application/json", **prepared.headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            print(f"{response.status} {response.read().decode()}")
            return 0
    except urllib.error.HTTPError as exc:
        print(f"error: the API answered {exc.code}", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"error: cannot reach {url}: {exc.reason}", file=sys.stderr)
    return 1


def _workspace_id(slug: str) -> uuid.UUID | None:
    with get_session_factory()() as session:
        workspace = identity_repo.get_workspace_by_slug(session, slug)
        if workspace is None:
            print(f"error: no workspace {slug!r}", file=sys.stderr)
            return None
        return workspace.id


def cmd_simulate_message(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.demo_tools_enabled:
        print("error: DEMO_TOOLS_ENABLED is false", file=sys.stderr)
        return 1
    workspace_id = _workspace_id(args.workspace)
    if workspace_id is None:
        return 1
    try:
        if args.script:
            script = simulator.get_script(args.script)
            alias, text, attachments = script.customer_alias, script.text, script.attachments
        elif args.customer and args.text:
            alias, text, attachments = args.customer, args.text, []
        else:
            print("error: give --script, or --customer and --text", file=sys.stderr)
            return 1
        prepared = simulator.prepare_customer_message(
            get_session_factory(),
            SystemClock(),
            settings,
            workspace_id,
            customer_alias=alias,
            text=text,
            attachments=attachments,
        )
    except AppError as exc:
        print(f"error: {exc.code}", file=sys.stderr)
        return 1
    return _post_webhook(settings, prepared)


def cmd_simulate_native_reply(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.demo_tools_enabled:
        print("error: DEMO_TOOLS_ENABLED is false", file=sys.stderr)
        return 1
    workspace_id = _workspace_id(args.workspace)
    if workspace_id is None:
        return 1
    try:
        prepared = simulator.prepare_native_reply(
            get_session_factory(),
            SystemClock(),
            settings,
            workspace_id,
            conversation_id=uuid.UUID(args.conversation),
            text=args.text,
        )
    except (AppError, ValueError) as exc:
        print(f"error: {getattr(exc, 'code', exc)}", file=sys.stderr)
        return 1
    return _post_webhook(settings, prepared)


def cmd_run_due_jobs(args: argparse.Namespace) -> int:
    ran = run_due_jobs(SystemClock(), session_factory=get_session_factory())
    print(f"ran {ran} due job(s)")
    return 0


def cmd_check_config(args: argparse.Namespace) -> int:
    try:
        settings = get_settings()
        if args.production:
            validate_production_settings(settings)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    if (
        args.require_separated_migration_credentials
        and not settings.has_separated_migration_credentials
    ):
        print(
            "error: MIGRATION_DATABASE_URL must use a distinct database role from DATABASE_URL.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(settings.public_dict(), indent=2, sort_keys=True, default=str))
    return 0


def cmd_migration_status(args: argparse.Namespace) -> int:
    revisions = list(migration_revisions())
    if args.head_only:
        payload: dict[str, object] = {
            "head_revision": migration_head(),
            "known_revisions": revisions,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    report = check_readiness()
    payload = {
        "current_revision": report.current_revision,
        "database": report.database,
        "head_revision": report.head_revision,
        "known_revisions": revisions,
        "migrations": report.migrations,
        "ready": report.ready,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.require_ready and not report.ready:
        return 1
    return 0


def cmd_post_restore_reconcile(args: argparse.Namespace) -> int:
    manifest: TombstoneManifest | None = None
    if args.tombstone_manifest:
        try:
            manifest = load_tombstone_manifest(Path(args.tombstone_manifest))
        except (OSError, ValueError) as exc:
            print(f"error: invalid tombstone manifest: {exc}", file=sys.stderr)
            return 1

    session_factory = get_session_factory()
    with session_factory() as session, session.begin():
        report = post_restore_reconcile(
            session,
            SystemClock().now(),
            tombstone_manifest=manifest,
        )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_verify_db_roles(args: argparse.Namespace) -> int:
    runtime_roles = tuple(
        role.strip() for role in (args.runtime_roles or "").split(",") if role.strip()
    )
    if not runtime_roles:
        print("error: --runtime-roles must name at least one role", file=sys.stderr)
        return 1
    session_factory = get_session_factory()
    with session_factory() as session, session.begin():
        if args.provision:
            provision_database_roles(
                session,
                migrator_role=args.migrator_role,
                app_role=runtime_roles[0],
                worker_role=runtime_roles[1] if len(runtime_roles) > 1 else runtime_roles[0],
                app_password=args.app_password,
                worker_password=args.worker_password,
            )
        report = verify_database_roles(
            session,
            migrator_role=args.migrator_role,
            runtime_roles=runtime_roles,
        )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.verified else 1


def run_telegram_polling(
    session_factory: Any,
    clock: Clock,
    settings: Settings,
    *,
    client: TelegramClient | None = None,
    timeout: int = 30,
    limit: int = 100,
    max_iterations: int | None = None,
) -> int:
    """Run long-polling loop for Telegram updates (ADR-012, Phase 9 Session 04)."""
    tg_client = client or TelegramClient()
    offset: int | None = None
    iterations = 0

    print(
        f"Starting Telegram long-polling harness (timeout={timeout}s, limit={limit})...",
        file=sys.stderr,
    )
    try:
        while max_iterations is None or iterations < max_iterations:
            iterations += 1
            try:
                updates = tg_client.get_updates(offset=offset, limit=limit, timeout=timeout)
            except Exception as exc:
                print(f"Error fetching Telegram updates: {exc}", file=sys.stderr)
                if max_iterations is not None:
                    break
                continue

            for raw_update in updates:
                update_id = raw_update.get("update_id")
                if update_id is not None:
                    offset = update_id + 1
                with session_factory() as session:
                    res = process_update(session, clock, raw_update, client=tg_client)
                    session.commit()
                    print(
                        f"Processed update {res.update_id}: "
                        f"status={res.status} action={res.action}",
                        file=sys.stderr,
                    )
    except KeyboardInterrupt:
        print("\nStopping Telegram polling.", file=sys.stderr)
    finally:
        if client is None:
            tg_client.close()
    return 0


def cmd_telegram_poll(args: argparse.Namespace) -> int:
    settings = get_settings()
    session_factory = get_session_factory()
    clock = SystemClock()
    max_iter = getattr(args, "max_iterations", None)
    timeout = getattr(args, "timeout", 30)
    limit = getattr(args, "limit", 100)
    return run_telegram_polling(
        session_factory,
        clock,
        settings,
        timeout=timeout,
        limit=limit,
        max_iterations=max_iter,
    )


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
        choices=("secret", "token-encryption", "backup-encryption"),
        default="secret",
        help=(
            "secret: a SECRET_KEY value; token-encryption: a TOKEN_ENCRYPTION_KEYS entry; "
            "backup-encryption: a BACKUP_ENCRYPTION_KEY entry"
        ),
    )
    p_key.add_argument(
        "--key-id",
        default=None,
        help="key id for --kind token-encryption (default k1) or backup-encryption (default b1)",
    )
    p_key.set_defaults(func=cmd_generate_key)

    p_api = sub.add_parser("export-openapi", help="print the OpenAPI document as JSON")
    p_api.add_argument("-o", "--output", help="write UTF-8 to this file instead of stdout")
    p_api.set_defaults(func=cmd_export_openapi)

    p_msg = sub.add_parser("simulate-message", help="send a simulated customer DM to the API")
    p_msg.add_argument("--workspace", required=True, help="workspace slug, e.g. golkent-fitness")
    p_msg.add_argument("--script", help="a script id from app/demo/scripts/customer_messages.yaml")
    p_msg.add_argument("--customer", help="customer name (with --text)")
    p_msg.add_argument("--text", help="message text (with --customer)")
    p_msg.set_defaults(func=cmd_simulate_message)

    p_native = sub.add_parser(
        "simulate-native-reply", help="simulate the owner answering in the Instagram app"
    )
    p_native.add_argument("--workspace", required=True)
    p_native.add_argument("--conversation", required=True, help="conversation id")
    p_native.add_argument("--text", required=True)
    p_native.set_defaults(func=cmd_simulate_native_reply)

    p_run = sub.add_parser("run-due-jobs", help="run the jobs that are due now, once")
    p_run.set_defaults(func=cmd_run_due_jobs)

    p_cfg = sub.add_parser(
        "check-config", help="validate configuration and print redacted public settings"
    )
    p_cfg.add_argument(
        "--production",
        action="store_true",
        help="require APP_ENV=production and all production startup safety checks",
    )
    p_cfg.add_argument(
        "--require-separated-migration-credentials",
        action="store_true",
        help="require MIGRATION_DATABASE_URL to use a distinct database role from DATABASE_URL",
    )
    p_cfg.set_defaults(func=cmd_check_config)

    p_mig = sub.add_parser(
        "migration-status", help="print Alembic migration head, known revisions, and DB readiness"
    )
    p_mig.add_argument(
        "--head-only",
        action="store_true",
        help="print code migration head and known revisions without connecting to the database",
    )
    p_mig.add_argument(
        "--require-ready",
        action="store_true",
        help="exit non-zero unless database is reachable and current_revision equals head_revision",
    )
    p_mig.set_defaults(func=cmd_migration_status)

    p_reconcile = sub.add_parser(
        "post-restore-reconcile",
        help="fence in-flight operations/drafts/agents and re-apply tombstones after restore",
    )
    p_reconcile.add_argument(
        "--tombstone-manifest",
        help="optional path to JSON tombstone manifest for post-snapshot erased entities",
    )
    p_reconcile.set_defaults(func=cmd_post_restore_reconcile)

    p_roles = sub.add_parser(
        "verify-db-roles",
        help="verify (and optionally provision) least-privilege runtime and migration DB roles",
    )
    p_roles.add_argument(
        "--migrator-role",
        default="agentnest_migrator",
        help="DDL/migration owner role (default: agentnest_migrator)",
    )
    p_roles.add_argument(
        "--runtime-roles",
        default="agentnest_app,agentnest_worker",
        help="comma-separated least-privilege runtime roles (default: agentnest_app,agentnest_worker)",  # noqa: E501
    )
    p_roles.add_argument(
        "--provision",
        action="store_true",
        help="provision roles and grants before verifying",
    )
    p_roles.add_argument("--app-password", default=None, help="optional password when provisioning")
    p_roles.add_argument(
        "--worker-password", default=None, help="optional password when provisioning"
    )
    p_roles.set_defaults(func=cmd_verify_db_roles)

    p_poll = sub.add_parser(
        "telegram-poll",
        help="run Telegram bot long-polling development harness",
    )
    p_poll.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="long-polling server timeout in seconds (default: 30)",
    )
    p_poll.add_argument(
        "--limit",
        type=int,
        default=100,
        help="max updates to retrieve per poll (default: 100)",
    )
    p_poll.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="optional maximum poll iterations before exit (for offline testing)",
    )
    p_poll.set_defaults(func=cmd_telegram_poll)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "migration-status" and getattr(args, "head_only", False):
        return int(args.func(args))
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
