"""Command line: ``python -m app.cli <command>``.

Commands: ``seed [--reset]``, ``create-user``, ``generate-key``, ``export-openapi``,
``simulate-message``, ``simulate-native-reply``, ``run-due-jobs`` (the developer simulator).
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

from app.core.clock import SystemClock
from app.core.config import ConfigError, Settings, get_settings
from app.core.db import get_session_factory
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.security import generate_encryption_key, generate_secret_key
from app.demo import simulator
from app.demo.seed import SeedError, seed
from app.identity import repository as identity_repo
from app.identity import service
from app.jobs.testing import run_due_jobs
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
