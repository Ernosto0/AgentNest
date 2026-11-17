import { useEffect, useId, useLayoutEffect, useRef, type ReactNode } from "react";
import { Link, Outlet, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChatIcon, CommentIcon, InfoIcon } from "@/components/icons";
import { useAgentOverviews, useHomeAttention } from "@/features/home/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { CommentsPage, QuestionsPage } from "@/features/agent-work/WorkPages";
import { ConversationList } from "./ConversationList";
import { useSocialAccounts } from "./hooks";
import { FOCUS, PANE, PaneEmpty } from "./InboxParts";

type Section = "messages" | "comments" | "questions";

/** Two panes from this width on; below it the list and the detail take turns. */
const SPLIT = 1024;

/**
 * Waiting counts for the Comments and Questions tabs, only where a real total exists
 * (unanswered comments; pending business questions across connected accounts). Messages has no
 * total (its list is a capped preview), so it shows none. Unknown counts are never shown as zero.
 */
function useTabCounts(ws: string): Partial<Record<Section, number>> {
  const accounts = useSocialAccounts(ws);
  const attention = useHomeAttention(ws);
  const overviews = useAgentOverviews(ws, accounts.data ?? []);
  const questionsKnown = accounts.isSuccess && overviews.every((q) => q.isSuccess);
  return {
    comments: attention.isSuccess ? attention.data.unanswered_comments : undefined,
    questions: questionsKnown ? overviews.reduce((sum, q) => sum + (q.data?.pending_questions ?? 0), 0) : undefined,
  };
}

/**
 * Comment actions require more than OAuth consent. The account's own capability flags decide,
 * the same gate the agent uses:
 * a real connection reports every `comment_*` capability as false. While accounts are loading or
 * absent, or an account reports no comment flags at all, nothing changes.
 */
function useCommentsUnavailable(ws: string): boolean {
  const accounts = useSocialAccounts(ws);
  if (!accounts.isSuccess || accounts.data.length === 0) return false;
  return accounts.data.every((account) => {
    const flags = Object.entries(account.capabilities).filter(([key]) => key.startsWith("comment_"));
    return flags.length > 0 && flags.every(([, on]) => on !== true);
  });
}

function SectionTab({ to, current, icon, label, count, note }: { to: string; current: boolean; icon: ReactNode; label: string; count?: number; note?: string }) {
  const { t } = useTranslation();
  const countId = useId();
  const shown = count !== undefined && count > 0;
  return (
    <Link
      to={to}
      aria-current={current ? "page" : undefined}
      aria-describedby={shown ? countId : undefined}
      className={`inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-lg px-3 text-body font-semibold whitespace-nowrap transition-colors pointer-coarse:min-h-11 sm:flex-none sm:px-3.5 ${FOCUS} ${
        current
          ? "bg-surface text-primary shadow-[0_1px_2px_rgb(37_59_49/0.10)] ring-1 ring-border"
          : "text-secondary hover:bg-surface/70 hover:text-primary"
      }`}
    >
      <span aria-hidden="true" className={`hidden text-base sm:inline ${current ? "text-action" : ""}`}>{icon}</span>
      {label}
      {shown ? (
        <>
          <span aria-hidden="true" className="min-w-5 rounded-full bg-attention-subtle px-1.5 text-center text-xs leading-5 font-bold text-attention tabular-nums">
            {count}
          </span>
          <span id={countId} className="sr-only">{t("convo.tabWaiting", { count })}</span>
        </>
      ) : null}
      {note ? <>{" "}<span className="rounded-full bg-surface-subtle px-2 text-xs leading-5 font-medium text-secondary ring-1 ring-border/70 ring-inset">{note}</span></> : null}
    </Link>
  );
}

/** Existing notification routes and new section links share one workspace. Public tabs mount no DM views. */
export function InboxWorkspace() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const { conversationId, questionId, threadId } = useParams();
  const location = useLocation();
  const [params] = useSearchParams();
  const raw = params.get("section");
  const section: Section = conversationId ? "messages" : location.pathname.includes("/comments") ? "comments" : location.pathname.includes("/questions") ? "questions" : raw === "comments" || raw === "questions" ? raw : "messages";
  const detail = Boolean(conversationId || questionId || threadId);
  const counts = useTabCounts(workspace.id);
  const commentsUnavailable = useCommentsUnavailable(workspace.id);
  const accounts = useSocialAccounts(workspace.id);
  const commentsNeedReconnect = accounts.data?.some((account) =>
    account.provider_kind === "meta" && account.status !== "disconnected" &&
    account.capabilities.comments_permission !== true,
  ) === true;
  const commentsNeedEnable = accounts.data?.some((account) =>
    account.provider_kind === "meta" && account.status !== "disconnected" &&
    account.capabilities.comments_permission === true,
  ) === true;
  const list = useRef<HTMLDivElement>(null);
  const scroll = useRef(0);
  const positions = useRef(new Map<string, number>());
  const filterKey = `${section}:${params.get("account") ?? ""}:${params.get("attention") ?? ""}:${params.get("cursor") ?? ""}`;
  useLayoutEffect(() => {
    if (list.current) list.current.scrollTop = positions.current.get(filterKey) ?? 0;
  }, [filterKey]);
  useEffect(() => {
    if (!detail && window.innerWidth < SPLIT) window.scrollTo({ top: scroll.current });
  }, [detail]);
  const target = (next: string) => {
    const query = new URLSearchParams();
    if (next !== "messages") query.set("section", next);
    if (params.get("account")) query.set("account", params.get("account")!);
    return `/w/${workspace.id}/inbox${query.size ? `?${query}` : ""}`;
  };
  const tabs: { name: Section; icon: ReactNode }[] = [
    { name: "messages", icon: <ChatIcon /> },
    { name: "comments", icon: <CommentIcon /> },
    { name: "questions", icon: <InfoIcon /> },
  ];
  return <div className="flex min-w-0 flex-col gap-5 pb-4">
    <header className="flex min-w-0 flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0 flex-1 basis-80">
        <h1 className="type-page break-words text-primary">{t("core.inbox")}</h1>
        <p className="mt-1.5 max-w-prose text-body text-secondary">{t(`convo.sectionIntro.${section}`)}</p>
      </div>
      <nav aria-label={t("core.inbox")} className="w-full sm:w-auto">
        <div className="flex gap-1 rounded-xl bg-surface-subtle p-1 ring-1 ring-border/70 ring-inset">
          {tabs.map(({ name, icon }) => (
            <SectionTab key={name} to={target(name)} current={section === name} icon={icon} label={t(`core.${name}`)} count={name === "comments" && commentsUnavailable ? undefined : counts[name]} note={name === "comments" && commentsUnavailable ? t("convo.commentsUnavailableTab") : undefined} />
          ))}
        </div>
      </nav>
    </header>
    <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[340px_minmax(0,1fr)]">
      <div
        ref={list}
        data-testid="inbox-list"
        onClickCapture={() => { if (!detail) scroll.current = window.scrollY; }}
        onScroll={event => positions.current.set(filterKey, event.currentTarget.scrollTop)}
        className={`${PANE} lg:sticky lg:top-24 lg:max-h-[calc(100dvh-8rem)] lg:overflow-y-auto lg:overscroll-contain ${detail ? "hidden lg:block" : ""}`}
      >
        {section === "messages" ? <ConversationList activeId={conversationId} /> : section === "comments" ? (commentsUnavailable ? <PaneEmpty testId="comments-unavailable" icon={<CommentIcon />} title={t("convo.commentsUnavailableTitle")} hint={t(commentsNeedReconnect ? "convo.commentsUnavailableReconnectHint" : commentsNeedEnable ? "convo.commentsUnavailableEnableHint" : "convo.commentsUnavailableHint")} /> : <CommentsPage />) : <QuestionsPage />}
      </div>
      <div className={`min-w-0 ${detail ? "" : "hidden lg:block"}`}><Outlet key={location.pathname} /></div>
    </div>
  </div>;
}
