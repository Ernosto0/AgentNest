"""CLI: ``uv run python -m evals run --all --provider fake``.

Exit status 1 when a hard assertion fails (always) or, with ``--strict``, when any case fails.
CI runs the fake provider with ``--strict``: the fake is deterministic, so every case must pass.
"""

import argparse
import sys
from pathlib import Path

from app.core.config import Settings
from app.integrations.llm import FakeLLMProvider, LLMProvider, build_provider
from evals.loader import EVALS_DIR, TASKS, load_datasets
from evals.report import write_reports
from evals.runner import TaskReport, run_task_evals


def _provider(name: str, settings: Settings) -> LLMProvider:
    if name == "fake":
        return FakeLLMProvider()
    chosen = settings.model_copy(update={"llm_provider": name})
    if not chosen.openai_api_key.get_secret_value():
        raise SystemExit("OPENAI_API_KEY is not set: cannot run the evals against OpenAI")
    return build_provider(chosen)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run eval datasets")
    group = run.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", choices=TASKS)
    group.add_argument("--all", action="store_true")
    run.add_argument("--provider", choices=("fake", "openai"), default="fake")
    run.add_argument("--dataset", help="only the dataset with this name")
    run.add_argument("--max-cost-usd", type=float, help="stop when the estimated cost exceeds this")
    run.add_argument("--report-dir", type=Path, default=EVALS_DIR / "reports")
    run.add_argument("--no-report", action="store_true", help="print only, write no files")
    run.add_argument("--strict", action="store_true", help="exit 1 if any case fails")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    settings = Settings()
    provider = _provider(args.provider, settings)
    tasks = TASKS if args.all else (args.task,)
    reports: list[TaskReport] = []
    for task in tasks:
        datasets = load_datasets(task, args.dataset)
        if not datasets:
            print(f"no datasets for {task}", file=sys.stderr)
            return 2
        model = "fake" if provider.is_fake else settings.llm_model_for(task)
        reports.append(
            run_task_evals(
                task, datasets, provider, model, settings, max_cost_usd=args.max_cost_usd
            )
        )

    failed = 0
    hard = 0
    for report in reports:
        m = report.metrics()
        print(
            f"{report.task}: {m['passed']}/{m['cases']} passed, "
            f"{m['hard_failures']} hard failures, model {report.model}"
        )
        for result in report.results:
            if not result.passed:
                marker = "HARD" if result in report.hard_failures else "soft"
                print(f"  [{marker}] {result.dataset}/{result.id}: {'; '.join(result.failures)}")
        if report.aborted:
            print(f"  {report.aborted}")
        failed += report.total - report.passed
        hard += len(report.hard_failures)
    if not args.no_report:
        json_path, md_path = write_reports(reports, args.report_dir, args.provider)
        print(f"report: {md_path}\n        {json_path}")
    if hard or any(r.aborted for r in reports):
        return 1
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
