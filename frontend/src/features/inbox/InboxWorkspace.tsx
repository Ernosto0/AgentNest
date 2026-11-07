import { useEffect, useLayoutEffect, useRef } from "react";
import { Link, Outlet, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/Layout";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { CommentsPage, QuestionsPage } from "@/features/agent-work/WorkPages";
import { ConversationList } from "./ConversationList";

/** Existing notification routes and new section links share one workspace. Public tabs mount no DM views. */
export function InboxWorkspace() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const { conversationId, questionId, threadId } = useParams();
  const location = useLocation();
  const [params] = useSearchParams();
  const raw = params.get("section");
  const section = conversationId ? "messages" : location.pathname.includes("/comments") ? "comments" : location.pathname.includes("/questions") ? "questions" : raw === "comments" || raw === "questions" ? raw : "messages";
  const detail = Boolean(conversationId || questionId || threadId);
  const list = useRef<HTMLDivElement>(null);
  const scroll = useRef(0);
  const positions = useRef(new Map<string, number>());
  const filterKey = `${section}:${params.get("account") ?? ""}:${params.get("attention") ?? ""}:${params.get("cursor") ?? ""}`;
  useLayoutEffect(() => {
    if (list.current) list.current.scrollTop = positions.current.get(filterKey) ?? 0;
  }, [filterKey]);
  useEffect(() => {
    if (!detail && window.innerWidth < 1200) window.scrollTo({ top: scroll.current });
  }, [detail]);
  const target = (next: string) => {
    const query = new URLSearchParams();
    if (next !== "messages") query.set("section", next);
    if (params.get("account")) query.set("account", params.get("account")!);
    return `/w/${workspace.id}/inbox${query.size ? `?${query}` : ""}`;
  };
  return <div className="flex min-w-0 flex-col gap-5">
    <PageHeader title={t("core.inbox")} />
    <nav aria-label={t("core.inbox")} className="flex flex-wrap gap-1 border-b border-border">
      {(["messages", "comments", "questions"] as const).map(name => <Link key={name} to={target(name)} aria-current={section === name ? "page" : undefined} className={`min-h-11 border-b-2 px-4 py-3 font-semibold focus-visible:outline-2 focus-visible:outline-focus ${section === name ? "border-action text-action" : "border-transparent text-secondary hover:bg-surface-subtle"}`}>{t(`core.${name}`)}</Link>)}
    </nav>
    <div className="grid min-w-0 items-start gap-6 min-[1200px]:grid-cols-[320px_minmax(0,1fr)]">
      <div ref={list} data-testid="inbox-list" onClickCapture={() => { if (!detail) scroll.current = window.scrollY; }} onScroll={event => positions.current.set(filterKey, event.currentTarget.scrollTop)} className={`min-w-0 min-[1200px]:sticky min-[1200px]:top-24 min-[1200px]:max-h-[calc(100dvh-8rem)] min-[1200px]:overflow-y-auto ${detail ? "hidden min-[1200px]:block" : ""}`}>
        {section === "messages" ? <ConversationList activeId={conversationId} /> : section === "comments" ? <CommentsPage /> : <QuestionsPage />}
      </div>
      <div className={`min-w-0 ${detail ? "" : "hidden min-[1200px]:block"}`}><Outlet key={location.pathname} /></div>
    </div>
  </div>;
}
