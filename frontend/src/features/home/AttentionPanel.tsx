import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ReportMetric, SocialAccount } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  AlertIcon,
  CheckIcon,
  ChevronRightIcon,
  CriticalIcon,
  HandIcon,
  InboxIcon,
  InfoIcon,
  LinkIcon,
  PencilIcon,
  ShieldCheckIcon,
} from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { Panel, PanelHeading, SkeletonRows } from "./DashboardPanel";
import { useHomeAttention, useRecentFailures, type useAgentOverviews } from "./hooks";

type Tone = "danger" | "attention" | "neutral";

const TONE: Record<Tone, { icon: string; count: string }> = {
  danger: { icon: "bg-danger-subtle text-danger", count: "bg-danger-subtle text-danger" },
  attention: { icon: "bg-attention-subtle text-attention", count: "bg-attention-subtle text-attention" },
  neutral: { icon: "bg-surface-subtle text-action", count: "bg-surface-subtle text-primary" },
};

/**
 * One thing that waits for the owner. The verb is the link; it is stretched over the whole
 * row so the row is one large target, while the accessible name stays the concrete action.
 */
function AttentionRow({
  testId,
  tone,
  icon,
  label,
  detail,
  verb,
  to,
  count,
}: {
  testId?: string;
  tone: Tone;
  icon: ReactNode;
  label: ReactNode;
  detail?: ReactNode;
  verb: string;
  to?: string;
  count?: ReactNode;
}) {
  return (
    <li
      data-testid={testId}
      className={`group/row relative flex min-w-0 items-center gap-3 rounded-xl px-2 py-2 transition-colors ${
        to ? "hover:bg-surface-subtle has-[a:focus-visible]:bg-surface-subtle has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-focus" : ""
      }`}
    >
      <span aria-hidden="true" className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-base ${TONE[tone].icon}`}>
        {icon}
      </span>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-body leading-snug font-medium text-primary [&>span:first-child]:line-clamp-2">
          {label}
        </span>
        {detail ? <span className="text-xs text-secondary">{detail}</span> : null}
        {to ? (
          <Link
            to={to}
            className="w-fit text-xs font-semibold text-action underline-offset-2 outline-none group-hover/row:underline after:absolute after:inset-0 after:rounded-xl after:content-['']"
          >
            {verb}
          </Link>
        ) : (
          <span className="text-xs text-secondary">{verb}</span>
        )}
      </div>
      {count !== undefined ? (
        <span className={`min-w-8 shrink-0 rounded-md px-2 py-0.5 text-center text-body font-bold tabular-nums ${TONE[tone].count}`}>
          {count}
        </span>
      ) : null}
      {to ? <ChevronRightIcon aria-hidden="true" className="shrink-0 text-base text-secondary/70 transition-transform group-hover/row:translate-x-0.5" /> : null}
    </li>
  );
}

/**
 * Needs your attention (ui-spec §4.2): connection recovery, failed posts, approvals, questions,
 * conversations, held content, drafts and comments, most urgent first. Unknown counts stay
 * "unavailable" and never produce the all-clear state.
 */
export function AttentionPanel({
  metrics,
  pending,
  error,
  accounts,
  overviews,
  className = "",
}: {
  metrics: Map<string, ReportMetric>;
  pending: boolean;
  error: Error | null;
  accounts: SocialAccount[];
  overviews: ReturnType<typeof useAgentOverviews>;
  className?: string;
}) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const base = `/w/${workspace.id}`;
  const failures = useRecentFailures(workspace.id);
  const attention = useHomeAttention(workspace.id);
  const isStaff = role === "staff";

  const questionsKnown = overviews.length === 0 || overviews.every((q) => q.isSuccess);
  const questionCount = questionsKnown ? overviews.reduce((sum, q) => sum + (q.data?.pending_questions ?? 0), 0) : null;

  const rows: { key: string; label: string; verb: string; to: string; staffHidden: boolean; tone: Tone; icon: ReactNode }[] = [
    { key: "pending_approvals_now", label: t("home.attention.approvals"), verb: t("core.reviewReply"), to: `${base}/approvals`, staffHidden: true, tone: "attention", icon: <ShieldCheckIcon /> },
    { key: "questions", label: t("core.questions"), verb: t("core.answerQuestion"), to: `${base}/more/agent/questions`, staffHidden: false, tone: "attention", icon: <InfoIcon /> },
    { key: "attention_now", label: t("home.attention.needsHuman"), verb: t("core.reviewReply"), to: `${base}/inbox?attention=needs_human`, staffHidden: false, tone: "attention", icon: <HandIcon /> },
    { key: "content_on_hold_now", label: t("home.attention.onHold"), verb: t("core.reviewContent"), to: `${base}/content?tab=problems`, staffHidden: true, tone: "attention", icon: <AlertIcon /> },
    { key: "drafts", label: t("home.attention.drafts"), verb: t("home.attention.reviewDrafts"), to: `${base}/content?tab=drafts`, staffHidden: true, tone: "neutral", icon: <PencilIcon /> },
    { key: "comments", label: t("home.attention.comments"), verb: t("home.attention.reviewComments"), to: `${base}/inbox?section=comments`, staffHidden: false, tone: "neutral", icon: <InboxIcon /> },
  ];
  const counted = rows
    .filter((row) => (!isStaff || !row.staffHidden) && (row.key === "questions" || row.key === "drafts" || row.key === "comments" || metrics.has(row.key)))
    .map((row) => {
      const count =
        row.key === "questions"
          ? questionCount
          : row.key === "drafts"
            ? attention.isSuccess ? attention.data.drafts : null
            : row.key === "comments"
              ? attention.isSuccess ? attention.data.unanswered_comments : null
              : metrics.get(row.key)?.value ?? null;
      return { ...row, count };
    });
  const open = counted.filter((row) => row.count !== 0);

  const reauthAccounts = accounts.filter((a) => a.status === "needs_reauth");
  const failed = isStaff ? [] : failures.data ?? [];
  const hasFailure = failed.length > 0;
  const loading = pending || attention.isPending || failures.isPending;
  const nothing =
    metrics.has("attention_now") &&
    (isStaff || ["pending_approvals_now", "content_on_hold_now"].every((key) => metrics.has(key))) &&
    !pending &&
    !error &&
    questionsKnown &&
    attention.isSuccess &&
    !accounts.some((a) => a.status === "needs_reauth" || a.status === "degraded") &&
    failures.isSuccess &&
    !hasFailure &&
    counted.every((row) => row.count === 0);

  // Urgent items (connection, failures, decisions, people) come first; review work follows a divider.
  const review = open.filter((row) => row.tone === "neutral");
  const urgentCount = reauthAccounts.length + failed.length + open.length - review.length;
  const total =
    open.every((row) => row.count !== null) && !loading
      ? open.reduce((sum, row) => sum + (row.count ?? 0), 0) + failed.length + reauthAccounts.length
      : null;

  return (
    <Panel aria-labelledby="home-attention-title" data-testid="home-attention" className={`gap-2.5 ${className}`}>
      <PanelHeading
        id="home-attention-title"
        title={t("home.attention.title")}
        meta={
          total !== null && total > 0 ? (
            <span className="mt-0.5 inline-flex items-center gap-1.5 rounded-full bg-attention-subtle px-2 py-px font-semibold text-attention">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-attention" />
              {t("home.attention.summary", { count: total })}
            </span>
          ) : undefined
        }
      />
      {error ? <ErrorMessage error={error} /> : null}
      {attention.error ? <ErrorMessage error={attention.error} /> : null}
      {!isStaff && failures.error ? <ErrorMessage error={failures.error} /> : null}
      {pending ? <SkeletonRows label={t("common.loading")} rows={3} /> : null}

      {nothing ? (
        <div
          data-testid="attention-none-state"
          className="flex items-center gap-3 rounded-xl bg-success-subtle/60 px-3 py-3"
        >
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-full bg-success text-base text-on-action">
            <CheckIcon />
          </span>
          <div>
            <p data-testid="attention-none" className="text-body font-semibold text-primary">
              {t("home.attention.none")}
            </p>
            <p className="text-xs text-secondary">{t("home.attention.noneHint")}</p>
          </div>
        </div>
      ) : null}

      <ul className="-mx-2 flex flex-col empty:hidden">
        {reauthAccounts.map((a) => (
          <AttentionRow
            key={a.id}
            tone="danger"
            icon={<LinkIcon />}
            label={`@${a.username}`}
            detail={t("home.attention.reauthShort")}
            verb={role === "owner" ? t("home.banner.reconnect") : t("automation.ownerOnly")}
            to={role === "owner" ? `${base}/more/settings/connections` : undefined}
          />
        ))}
        {failed.map((item) => (
          <AttentionRow
            key={item.id}
            tone="danger"
            icon={<CriticalIcon />}
            label={
              <>
                <span className="min-w-0 [overflow-wrap:anywhere]">{item.title}</span>
                {item.is_simulated ? <SimulatedBadge compact /> : null}
              </>
            }
            detail={t("home.attention.failedDetail")}
            verb={t("core.fixPost")}
            to={`${base}/content/${item.id}`}
          />
        ))}
        {open.filter((row) => row.tone !== "neutral").map((row) => (
          <AttentionRow
            key={row.key}
            testId={`attention-${row.key}`}
            tone={row.tone}
            icon={row.icon}
            label={<span>{row.label}</span>}
            verb={row.verb}
            to={row.to}
            count={row.count ?? t("core.unavailable")}
          />
        ))}
      </ul>
      {review.length > 0 ? (
        <ul className={`-mx-2 flex flex-col ${urgentCount > 0 ? "border-t border-border pt-2" : ""}`}>
          {review.map((row) => (
            <AttentionRow
              key={row.key}
              testId={`attention-${row.key}`}
              tone={row.tone}
              icon={row.icon}
              label={<span>{row.label}</span>}
              verb={row.verb}
              to={row.to}
              count={row.count ?? t("core.unavailable")}
            />
          ))}
        </ul>
      ) : null}
      {hasFailure ? <p className="text-metadata text-secondary">{t("core.previewList")}</p> : null}
      {overviews.some((q) => q.isError) ? (
        <p role="status" className="text-metadata text-secondary">
          {t("core.questions")}: {t("core.unavailable")}
        </p>
      ) : null}
    </Panel>
  );
}
