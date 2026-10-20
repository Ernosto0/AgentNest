import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AppError, localizeError } from "@/api/errors";
import type { Command } from "@/api/types";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { describeResult, linkPath, type ResultLink } from "./messages";

const LINK =
  "inline-flex min-h-11 items-center text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600";

/** Why a post is on hold or failing, when the status question has an answer beyond its state. */
function ContentStatusExtra({ params }: { params: Record<string, unknown> }) {
  const { t } = useTranslation();
  const hold = params.hold_reason;
  const code = params.error_code;
  if (params.status === "on_hold" && (hold === "FACT_CHANGED" || hold === "ACCOUNT_UNAVAILABLE")) {
    return <p className="text-sm">{t(`content.hold.${hold}.what`)}</p>;
  }
  if ((params.status === "failed" || params.status === "retry_scheduled") && typeof code === "string") {
    const what = t(`errors.${code}.what`, { defaultValue: "" });
    return what ? <p className="text-sm">{what}</p> : null;
  }
  return null;
}

/**
 * `query.explain_failure`: the server already wrote what happened and what to do in the user's
 * language, from the error catalog. A retry says when; a failure says nothing more is tried.
 */
function ContentFailureResult({
  params,
  linkList,
}: {
  params: Record<string, unknown>;
  linkList: ReactNode;
}) {
  const { t } = useTranslation();
  const status = params.status;
  const retryAt = typeof params.retry_at === "string" && params.retry_at !== "" ? params.retry_at : null;
  const when = typeof params.when === "string" && params.when !== "" ? params.when : null;
  return (
    <div className="flex flex-col gap-1" data-testid="command-result" data-status="completed" data-kind="content-failure">
      <p className="font-medium">
        {t("command.msg.content_failure_title", { title: String(params.title ?? "") })}
        {params.is_simulated === true ? (
          <>
            {" "}
            <SimulatedBadge />
          </>
        ) : null}
      </p>
      <p>{String(params.what ?? "")}</p>
      <p>{String(params.next ?? "")}</p>
      {status === "retry_scheduled" ? (
        <p className="text-sm font-medium">
          {retryAt ? t("command.msg.failureRetryAt", { time: retryAt }) : t("command.msg.failureRetryable")}
        </p>
      ) : null}
      {status === "failed" ? <p className="text-sm font-medium">{t("command.msg.failureFinal")}</p> : null}
      {when ? <p className="text-sm text-slate-600">{t("command.msg.failureWhen", { when })}</p> : null}
      {linkList}
    </div>
  );
}

/**
 * `query.explain_failure` about a reply that did not go out: what happened, when (the server
 * formats it in the workspace time zone) and what to do next, all from the error catalog. The
 * text never comes from the provider, and an unconfirmed send says to check before resending.
 */
function ReplyFailureResult({
  params,
  linkList,
}: {
  params: Record<string, unknown>;
  linkList: ReactNode;
}) {
  const { t } = useTranslation();
  const when = typeof params.when === "string" && params.when !== "" ? params.when : null;
  return (
    <div className="flex flex-col gap-1" data-testid="command-result" data-status="completed" data-kind="reply-failure">
      <p className="font-medium">
        {t("command.msg.reply_failure_title")}
        {params.is_simulated === true ? (
          <>
            {" "}
            <SimulatedBadge />
          </>
        ) : null}
      </p>
      <p>{String(params.what ?? "")}</p>
      <p>{String(params.next ?? "")}</p>
      {when ? <p className="text-sm text-slate-600">{t("command.msg.failureWhen", { when })}</p> : null}
      <p className="text-sm font-medium">{t("command.msg.failureFinal")}</p>
      {linkList}
    </div>
  );
}

/** The outcome of a command: an answer, a refusal with a pointer into the app, or a failure. */
export function CommandResultCard({ command }: { command: Command }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const result = command.result;
  const links = (result?.links ?? []) as unknown as ResultLink[]; // structured by the API

  const linkList = links.length ? (
    <ul className="flex flex-wrap gap-x-4">
      {links.map((link) => (
        <li key={`${link.target}:${link.key ?? ""}:${link.id ?? ""}:${link.date ?? ""}`}>
          <Link to={linkPath(workspace.id, link)} className={LINK}>
            {link.target === "content" && link.id
              ? t("command.link.content_item")
              : link.target === "inbox" && link.id
                ? t("command.link.conversation")
                : t(`command.link.${link.target}`, { defaultValue: t("command.link.knowledge") })}
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

  if (result && result.message_key === "command.content_failure") {
    return <ContentFailureResult params={result.params} linkList={linkList} />;
  }
  if (result && result.message_key === "command.reply_failure") {
    return <ReplyFailureResult params={result.params} linkList={linkList} />;
  }

  if (result) {
    // Content answers describe one item; a simulated one says so (INV-09).
    const simulated = result.params.is_simulated === true;
    return (
      <div className="flex flex-col gap-2" data-testid="command-result" data-status={command.status}>
        <p className="font-medium">
          {describeResult(t, result.message_key, result.params)}
          {simulated ? (
            <>
              {" "}
              <SimulatedBadge />
            </>
          ) : null}
        </p>
        {result.message_key === "command.content_status" ? <ContentStatusExtra params={result.params} /> : null}
        {linkList}
      </div>
    );
  }
  return null;
}
