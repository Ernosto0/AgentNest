import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronRightIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { WindowTimer } from "./DraftParts";
import { useConversations, useSocialAccounts, type AttentionFilter } from "./hooks";
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
  const accounts = useSocialAccounts(workspace.id);
  const navigate = useNavigate();
  const account = searchParams.get("account");
  const shown = conversations.data?.filter(c => !account || c.social_account_id === account);

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <h2 className="type-section">{t("core.messages")}</h2>
      {accounts.data && accounts.data.length > 1 ? <label className="flex flex-col gap-2 font-medium"><span>{t("agent.account")}</span><select value={account ?? ""} className="min-h-11 w-full rounded-control border border-control bg-surface p-2" onChange={e => { const next = new URLSearchParams(searchParams); if (e.target.value) next.set("account", e.target.value); else next.delete("account"); navigate(`/w/${workspace.id}/inbox?${next}`); }}><option value="">{t("core.allAccounts")}</option>{accounts.data.map(a => <option key={a.id} value={a.id}>@{a.username ?? t("agent.account")}</option>)}</select></label> : null}
      <p className="text-metadata text-secondary">{t("core.previewOnly")}</p>

      <div role="group" aria-label={t("convo.filters.label")} className="flex flex-wrap gap-1 border-b border-border">
        {FILTERS.map((name) => {
          const isSelected = filter === name;
          return (
            <button
              key={name}
              type="button"
              aria-pressed={isSelected}
              onClick={() => setFilter(name)}
              className={`min-h-11 border-b-2 px-3 py-2 text-body font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                isSelected
                  ? "border-action text-action"
                  : "border-transparent text-secondary hover:text-primary hover:bg-surface-subtle"
              }`}
            >
              {t(`convo.filters.${name}`)}
            </button>
          );
        })}
      </div>

      {conversations.isError ? <ErrorMessage error={conversations.error} /> : null}
      {conversations.isPending ? <p className="text-body text-secondary">{t("common.loading")}</p> : null}
      {shown && shown.length === 0 ? (
        <EmptyState title={t("convo.empty")} description={t("convo.emptyHint")} />
      ) : null}
      {shown && shown.length > 0 ? (
        <Card className="overflow-hidden p-0">
          <ul className="flex flex-col divide-y divide-border" aria-label={t("convo.title")}>
            {shown.map((conversation) => {
              const label = customerLabel(conversation, t);
              const initials = getInitials(label);
              const isSelected = activeId === conversation.id;

              return (
                <li key={conversation.id}>
                  <Link
                    to={`/w/${workspace.id}/inbox/${conversation.id}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`}
                    data-conversation-id={conversation.id}
                    aria-current={isSelected ? "true" : undefined}
                    className={`flex min-h-16 items-center justify-between gap-3.5 p-4 transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus ${
                      isSelected
                        ? "bg-assistant border-l-4 border-l-action"
                        : "bg-surface hover:bg-surface-subtle"
                    }`}
                  >
                    <div className="flex items-start gap-3.5 min-w-0">
                      <div
                        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-xs font-extrabold tracking-tight transition-colors shadow-2xs ${
                          isSelected
                            ? "bg-action text-on-action"
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
                              className="inline-flex items-center rounded-control bg-attention-subtle px-2 py-0.5 text-xs font-medium text-attention"
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
