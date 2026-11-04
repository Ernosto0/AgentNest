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
        <h1 className="text-2xl font-bold tracking-tight text-primary">{t("convo.title")}</h1>
        <p className="mt-1 text-body text-secondary">{t("convo.intro")}</p>
      </div>

      <div role="tablist" aria-label={t("convo.filters.label")} className="flex flex-wrap gap-1.5 p-1 bg-surface-subtle/80 rounded-xl border border-border/70 shadow-2xs">
        {FILTERS.map((name) => {
          const isSelected = filter === name;
          return (
            <button
              key={name}
              role="tab"
              type="button"
              aria-selected={isSelected}
              onClick={() => setFilter(name)}
              className={`min-h-9 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                isSelected
                  ? "bg-surface text-primary shadow-xs font-bold"
                  : "text-secondary hover:text-primary hover:bg-surface/50"
              }`}
            >
              {t(`convo.filters.${name}`)}
            </button>
          );
        })}
      </div>

      {conversations.isError ? <ErrorMessage error={conversations.error} /> : null}
      {conversations.isPending ? <p className="text-body text-secondary">{t("common.loading")}</p> : null}
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
                    className={`flex min-h-16 items-center justify-between gap-3.5 rounded-2xl p-4 border transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                      isSelected
                        ? "bg-surface border-action shadow-card-hover ring-1 ring-action/20 border-l-4 border-l-action"
                        : "bg-surface border-border/80 shadow-2xs hover:bg-surface hover:border-action/40 hover:shadow-card-modern hover:translate-y-[-1px]"
                    }`}
                  >
                    <div className="flex items-start gap-3.5 min-w-0">
                      <div
                        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-xs font-extrabold tracking-tight transition-colors shadow-2xs ${
                          isSelected
                            ? "bg-gradient-to-br from-action to-action-hover text-on-action shadow-xs ring-1 ring-emerald-500/30"
                            : "bg-surface-subtle text-primary border border-border"
                        }`}
                        aria-hidden="true"
                      >
                        {initials}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="block font-bold text-primary truncate text-sm">{label}</span>
                        </div>
                        <span className="block truncate text-body text-secondary mt-0.5">
                          {conversation.last_message_preview ?? t("convo.noPreview")}
                        </span>
                        <span className="mt-2 flex flex-wrap items-center gap-1.5 text-metadata">
                          {conversation.attention !== "none" ? (
                            <span
                              data-testid="attention-chip"
                              className="inline-flex items-center rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-bold text-amber-800 border border-amber-500/30 shadow-2xs"
                            >
                              {t(`convo.attention.${conversation.attention}`)}
                            </span>
                          ) : null}
                          {conversation.handling_mode === "human" ? (
                            <span className="inline-flex items-center rounded-full bg-surface-subtle px-2 py-0.5 text-xs font-semibold text-secondary border border-border">
                              {t("convo.handledByYou")}
                            </span>
                          ) : null}
                          <WindowTimer endsAt={conversation.window_ends_at} />
                          {conversation.is_simulated ? <SimulatedBadge /> : null}
                        </span>
                      </div>
                    </div>
                    <ChevronRightIcon
                      className={`shrink-0 text-xl transition-transform ${isSelected ? "text-action translate-x-0.5" : "text-secondary/40"}`}
                    />
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
