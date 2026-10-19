import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AppError, localizeError } from "@/api/errors";
import type { Command } from "@/api/types";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { describeResult, linkPath, type ResultLink } from "./messages";

const LINK =
  "inline-flex min-h-11 items-center text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600";

/** The outcome of a command: an answer, a refusal with a pointer into the app, or a failure. */
export function CommandResultCard({ command }: { command: Command }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const result = command.result;
  const links = (result?.links ?? []) as unknown as ResultLink[]; // structured by the API

  const linkList = links.length ? (
    <ul className="flex flex-wrap gap-x-4">
      {links.map((link) => (
        <li key={`${link.target}:${link.key ?? ""}`}>
          <Link to={linkPath(workspace.id, link)} className={LINK}>
            {t(`command.link.${link.target}`, { defaultValue: t("command.link.knowledge") })}
          </Link>
        </li>
      ))}
    </ul>
  ) : null;

  if (command.status === "cancelled" || command.status === "expired") {
    return <p data-testid="command-result">{t(`command.status.${command.status}`)}</p>;
  }

  if (command.status === "unsupported" && result) {
    const params = result.params as { reason?: string; suggestions?: string[] };
    const reason = params.reason ?? "other";
    return (
      <div className="flex flex-col gap-2" data-testid="command-result" data-status="unsupported">
        <p className="font-medium">{t("command.unsupported.title")}</p>
        <p>{t(`command.unsupported.reason.${reason}`, { defaultValue: t("command.unsupported.reason.other") })}</p>
        {linkList}
        {params.suggestions?.length ? (
          <div>
            <p className="text-sm text-slate-600">{t("command.unsupported.suggestionsTitle")}</p>
            <ul className="list-disc pl-5 text-sm">
              {params.suggestions.map((key) => (
                <li key={key}>{t(`command.${key.replace(/^command\./, "")}`)}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  }

  if (command.status === "failed") {
    const code = command.error_code ?? "UNKNOWN";
    const { what, next } = localizeError(new AppError(code, 0), t);
    const detail = result && result.message_key !== "command.failed"
      ? describeResult(t, result.message_key, result.params)
      : null;
    return (
      <div role="alert" className="flex flex-col gap-1" data-testid="command-result" data-status="failed" data-error={code}>
        {detail ? <p className="font-medium">{detail}</p> : <p className="font-medium">{what}</p>}
        {detail ? null : <p>{next}</p>}
        {linkList}
      </div>
    );
  }

  if (result) {
    const note = result.message_key === "command.activity_basic" ? t("command.msg.activity_basic_note") : null;
    return (
      <div className="flex flex-col gap-2" data-testid="command-result" data-status={command.status}>
        <p className="font-medium">{describeResult(t, result.message_key, result.params)}</p>
        {note ? <p className="text-sm text-slate-600">{note}</p> : null}
        {linkList}
      </div>
    );
  }
  return null;
}
