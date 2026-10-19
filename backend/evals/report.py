"""JSON and Markdown reports under ``evals/reports/`` (ADR-018)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from evals.runner import TaskReport


def render_markdown(reports: list[TaskReport], generated_at: datetime) -> str:
    lines = [f"# AI evaluation report ({generated_at:%Y-%m-%d %H:%M} UTC)", ""]
    for report in reports:
        m = report.metrics()
        lines += [
            f"## {report.task}",
            "",
            f"- provider `{report.provider}`, model `{report.model}`, "
            f"prompt `{report.prompt_version}`, datasets: {', '.join(report.datasets)}",
            f"- cases: **{m['passed']}/{m['cases']}** passed (accuracy {m['accuracy']})",
            f"- hard-assertion failures: **{m['hard_failures']}** (must be 0)",
            "- forbidden requests handled: "
            f"{m['forbidden_requests_handled']}/{m['forbidden_requests']}",
            f"- invalid-output rate {m['invalid_output_rate']}, repair rate {m['repair_rate']}",
            f"- tokens in/out: {m['input_tokens']}/{m['output_tokens']}, "
            f"latency mean {m['latency_ms_mean']} ms, p95 {m['latency_ms_p95']} ms, "
            f"estimated cost {m['estimated_cost_usd']} USD",
        ]
        if report.aborted:
            lines.append(f"- **{report.aborted}**")
        failed = [r for r in report.results if not r.passed]
        if failed:
            lines += ["", "| case | hard | failures |", "|---|---|---|"]
            for r in failed:
                lines.append(
                    f"| {r.dataset}/{r.id} | {'yes' if r.hard else ''} | {'; '.join(r.failures)} |"
                )
        else:
            lines += ["", "All cases passed."]
        lines.append("")
    return "\n".join(lines)


def write_reports(reports: list[TaskReport], directory: Path, label: str) -> tuple[Path, Path]:
    """Write ``<timestamp>-<label>.json`` and ``.md``; returns both paths."""
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    stem = f"{now:%Y%m%dT%H%M%SZ}-{label}"
    json_path, md_path = directory / f"{stem}.json", directory / f"{stem}.md"
    json_path.write_text(
        json.dumps(
            {"generated_at": now.isoformat(), "reports": [r.to_dict() for r in reports]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(reports, now), encoding="utf-8")
    return json_path, md_path
