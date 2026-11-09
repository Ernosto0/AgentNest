import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AppError, localizeError } from "@/api/errors";
import type { Command } from "@/api/types";
import { CriticalIcon, InfoIcon, LinkIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { describeResult, linkPath, type ResultLink } from "./messages";

const LINK =
  "inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-action/30 bg-action/5 px-3 py-1.5 text-xs font-semibold text-action transition-all hover:bg-action hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus cursor-pointer shadow-2xs";

/** Why a post is on hold or failing, when the status question has an answer beyond its state. */
function ContentStatusExtra({ params }: { params: Record<string, unknown> }) {
  const { t } = useTranslation();
  const hold = params.hold_reason;
  const code = params.error_code;
  if (params.status === "on_hold" && (hold === "FACT_CHANGED" || hold === "ACCOUNT_UNAVAILABLE")) {
    return <p className="text-body text-secondary mt-1">{t(`content.hold.${hold}.what`)}</p>;
  }
  if ((params.status === "failed" || params.status === "retry_scheduled") && typeof code === "string") {
    const what = t(`errors.${code}.what`, { defaultValue: "" });
    return what ? <p className="text-body text-secondary mt-1">{what}</p> : null;
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
    <div
      className="flex flex-col gap-2 rounded-xl border border-danger/30 bg-danger-subtle/50 p-4"
      data-testid="command-result"
      data-status="completed"
      data-kind="content-failure"
    >
      <div className="flex items-center gap-2">
        <CriticalIcon className="text-base text-danger shrink-0" />
        <p className="font-heading font-semibold text-danger">
          {t("command.msg.content_failure_title", { title: String(params.title ?? "") })}
          {params.is_simulated === true ? (
            <>
              {" "}
              <SimulatedBadge />
            </>
          ) : null}
        </p>
      </div>
      <p className="text-body font-medium text-primary">{String(params.what ?? "")}</p>
      <p className="text-body text-secondary">{String(params.next ?? "")}</p>
      {status === "retry_scheduled" ? (
        <p className="text-metadata font-medium text-attention">
          {retryAt ? t("command.msg.failureRetryAt", { time: retryAt }) : t("command.msg.failureRetryable")}
        </p>
      ) : null}
      {status === "failed" ? <p className="text-metadata font-semibold text-danger">{t("command.msg.failureFinal")}</p> : null}
      {when ? <p className="text-metadata text-secondary">{t("command.msg.failureWhen", { when })}</p> : null}
      {linkList ? <div className="pt-1">{linkList}</div> : null}
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
    <div
      className="flex flex-col gap-2 rounded-xl border border-danger/30 bg-danger-subtle/50 p-4"
      data-testid="command-result"
      data-status="completed"
      data-kind="reply-failure"
    >
      <div className="flex items-center gap-2">
        <CriticalIcon className="text-base text-danger shrink-0" />
        <p className="font-heading font-semibold text-danger">
          {t("command.msg.reply_failure_title")}
          {params.is_simulated === true ? (
            <>
              {" "}
              <SimulatedBadge />
            </>
          ) : null}
        </p>
      </div>
      <p className="text-body font-medium text-primary">{String(params.what ?? "")}</p>
      <p className="text-body text-secondary">{String(params.next ?? "")}</p>
      {when ? <p className="text-metadata text-secondary">{t("command.msg.failureWhen", { when })}</p> : null}
      <p className="text-metadata font-semibold text-danger">{t("command.msg.failureFinal")}</p>
      {linkList ? <div className="pt-1">{linkList}</div> : null}
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
    <ul className="flex flex-wrap gap-2 pt-1">
      {links.map((link) => (
        <li key={`${link.target}:${link.key ?? ""}:${link.id ?? ""}:${link.date ?? ""}`}>
          <Link to={linkPath(workspace.id, link)} className={LINK}>
            <LinkIcon className="text-xs shrink-0" />
            <span>
              {link.target === "content" && link.id
                ? t("command.link.content_item")
                : link.target === "inbox" && link.id
                  ? t("command.link.conversation")
                  : t(`command.link.${link.target}`, { defaultValue: t("command.link.knowledge") })}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  ) : null;

  if (command.status === "cancelled" || command.status === "expired") {
    return (
      <div
        data-testid="command-result"
        className="flex items-center gap-2 rounded-xl border border-border/80 bg-surface-subtle/40 p-3.5 text-body text-secondary"
      >
        <span className="font-medium">{t(`command.status.${command.status}`)}</span>
      </div>
    );
  }

  if (command.status === "unsupported" && result) {
    const params = result.params as { reason?: string; suggestions?: string[]; reply_text?: string };
    const replyText = (result as { reply_text?: string }).reply_text || params.reply_text;
    const reason = params.reason ?? "other";

    if (replyText) {
      return (
        <div className="flex flex-col gap-3" data-testid="command-result" data-status="unsupported">
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-attention/10 text-attention mt-0.5 ring-1 ring-attention/20">
              <InfoIcon className="text-base" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-base font-medium text-primary leading-relaxed">{replyText}</p>
              {linkList ? <div className="mt-2">{linkList}</div> : null}
              {params.suggestions?.length ? (
                <div className="mt-3 flex flex-col gap-2 rounded-xl border border-border/80 bg-surface-subtle/50 p-3.5">
                  <p className="text-2xs font-semibold uppercase tracking-wider text-secondary">
                    {t("command.unsupported.suggestionsTitle")}
                  </p>
                  <ul className="flex flex-wrap gap-1.5">
                    {params.suggestions.map((key) => (
                      <li key={key} className="inline-flex items-center rounded-lg border border-border/80 bg-surface px-2.5 py-1 text-xs text-primary font-medium">
                        {t(`command.${key.replace(/^command\./, "")}`)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div
        className="flex flex-col gap-2.5 rounded-xl border border-attention/30 bg-attention-subtle/50 p-4 text-primary"
        data-testid="command-result"
        data-status="unsupported"
      >
        <div className="flex items-center gap-2">
          <InfoIcon className="text-base text-attention shrink-0" />
          <p className="font-heading font-semibold text-attention">{t("command.unsupported.title")}</p>
        </div>
        <p className="text-body text-primary font-medium">
          {t(`command.unsupported.reason.${reason}`, { defaultValue: t("command.unsupported.reason.other") })}
        </p>
        {linkList}
        {params.suggestions?.length ? (
          <div className="mt-2 flex flex-col gap-2 pt-2 border-t border-attention/20">
            <p className="text-2xs font-semibold uppercase tracking-wider text-secondary">
              {t("command.unsupported.suggestionsTitle")}
            </p>
            <ul className="flex flex-wrap gap-1.5">
              {params.suggestions.map((key) => (
                <li key={key} className="inline-flex items-center rounded-lg border border-border/80 bg-surface px-2.5 py-1 text-xs text-primary font-medium">
                  {t(`command.${key.replace(/^command\./, "")}`)}
                </li>
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
    const detail =
      result && result.message_key !== "command.failed" ? describeResult(t, result.message_key, result.params) : null;
    return (
      <div
        role="alert"
        className="flex flex-col gap-2 rounded-xl border border-danger/30 bg-danger-subtle/50 p-4 text-primary"
        data-testid="command-result"
        data-status="failed"
        data-error={code}
      >
        <div className="flex items-center gap-2">
          <CriticalIcon className="text-base text-danger shrink-0" />
          {detail ? (
            <p className="font-heading font-semibold text-danger">{detail}</p>
          ) : (
            <p className="font-heading font-semibold text-danger">{what}</p>
          )}
        </div>
        {detail ? null : <p className="text-body text-primary">{next}</p>}
        {linkList ? <div className="pt-1">{linkList}</div> : null}
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
    const directReply =
      (result as { reply_text?: string }).reply_text ||
      (result.params as { reply_text?: string })?.reply_text;
    return (
      <div className="flex flex-col gap-3" data-testid="command-result" data-status={command.status}>
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-action/10 text-action mt-0.5 ring-1 ring-action/20 shadow-2xs">
            <SparkIcon className="text-base" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-base font-medium leading-relaxed text-primary break-words">
              {directReply || describeResult(t, result.message_key, result.params)}
              {simulated ? (
                <>
                  {" "}
                  <SimulatedBadge />
                </>
              ) : null}
            </p>
            {result.message_key === "command.content_status" ? (
              <ContentStatusExtra params={result.params} />
            ) : null}
          </div>
        </div>
        {linkList ? <div className="sm:pl-11">{linkList}</div> : null}
      </div>
    );
  }
  return null;
}
