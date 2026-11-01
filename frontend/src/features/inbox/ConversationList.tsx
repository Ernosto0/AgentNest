import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronRightIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { WindowTimer } from "./DraftParts";
import { useConversations, type AttentionFilter } from "./hooks";
import { customerLabel } from "./labels";

const FILTERS: AttentionFilter[] = ["any", "needs_approval", "needs_human", "failed"];

function getInitials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  if (trimmed.startsWith("Müşteri #") || trimmed.startsWith("Customer #")) {
    const num = trimmed.replace(/[^0-9]/g, "");
    return num ? `#${num.slice(-2)}` : "#";
  }
  const parts = trimmed.split(/\s+/);
  if (parts.length >= 2) {
    return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase();
  }
  return trimmed.slice(0, 2).toUpperCase();
}

interface ConversationListProps {
  activeId?: string;
  className?: string;
}

export function ConversationList({ activeId, className = "" }: ConversationListProps) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();

  const rawFilter = searchParams.get("attention");
  const filter: AttentionFilter =
    rawFilter && FILTERS.includes(rawFilter as AttentionFilter) ? (rawFilter as AttentionFilter) : "any";

  const setFilter = (next: AttentionFilter) => {
    const nextParams = new URLSearchParams(searchParams);
    if (next === "any") {
      nextParams.delete("attention");
    } else {
      nextParams.set("attention", next);
    }
    setSearchParams(nextParams);
  };

  const conversations = useConversations(workspace.id, filter);

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{t("convo.title")}</h1>
        <p className="mt-1 text-sm text-slate-600">{t("convo.intro")}</p>
      </div>

      <div role="tablist" aria-label={t("convo.filters.label")} className="flex flex-wrap gap-1.5">
        {FILTERS.map((name) => {
          const isSelected = filter === name;
          return (
            <button
              key={name}
              role="tab"
              type="button"
              aria-selected={isSelected}
              onClick={() => setFilter(name)}
              className={`min-h-10 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                isSelected
                  ? "bg-indigo-700 text-white shadow-xs"
                  : "bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {t(`convo.filters.${name}`)}
            </button>
          );
        })}
      </div>

      {conversations.isError ? <ErrorMessage error={conversations.error} /> : null}
      {conversations.isPending ? <p className="text-sm text-slate-500">{t("common.loading")}</p> : null}
      {conversations.data && conversations.data.length === 0 ? (
        <EmptyState title={t("convo.empty")} description={t("convo.emptyHint")} />
      ) : null}
      {conversations.data && conversations.data.length > 0 ? (
        <Card className="p-0 border-0 bg-transparent shadow-none ring-0">
          <ul className="flex flex-col gap-2.5" aria-label={t("convo.title")}>
            {conversations.data.map((conversation) => {
              const label = customerLabel(conversation, t);
              const initials = getInitials(label);
              const isSelected = activeId === conversation.id;

              return (
                <li key={conversation.id}>
                  <Link
                    to={`/w/${workspace.id}/inbox/${conversation.id}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`}
                    data-conversation-id={conversation.id}
                    aria-current={isSelected ? "true" : undefined}
                    className={`flex min-h-16 items-center justify-between gap-3.5 rounded-xl p-3.5 ring-1 transition-all focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                      isSelected
                        ? "bg-indigo-50/90 ring-2 ring-indigo-600 shadow-xs"
                        : "bg-white ring-slate-200 hover:bg-slate-50 hover:ring-slate-300"
                    }`}
                  >
                    <div className="flex items-start gap-3 min-w-0">
                      <div
                        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xs font-bold tracking-tight ${
                          isSelected ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-700 ring-1 ring-slate-200"
                        }`}
                        aria-hidden="true"
                      >
                        {initials}
                      </div>
                      <div className="min-w-0 flex-1">
                        <span className="block font-semibold text-slate-900 truncate">{label}</span>
                        <span className="block truncate text-sm text-slate-600">
                          {conversation.last_message_preview ?? t("convo.noPreview")}
                        </span>
                        <span className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                          {conversation.attention !== "none" ? (
                            <span
                              data-testid="attention-chip"
                              className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-900"
                            >
                              {t(`convo.attention.${conversation.attention}`)}
                            </span>
                          ) : null}
                          {conversation.handling_mode === "human" ? (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700 ring-1 ring-slate-200">
                              {t("convo.handledByYou")}
                            </span>
                          ) : null}
                          <WindowTimer endsAt={conversation.window_ends_at} />
                          {conversation.is_simulated ? <SimulatedBadge /> : null}
                        </span>
                      </div>
                    </div>
                    <ChevronRightIcon className={`shrink-0 text-xl transition-colors ${isSelected ? "text-indigo-600" : "text-slate-400"}`} />
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

