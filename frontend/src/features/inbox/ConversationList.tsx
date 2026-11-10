import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import type { Conversation } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChatIcon, HandIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { SkeletonRows } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { WindowTimer } from "./DraftParts";
import { useConversations, useSocialAccounts, type AttentionFilter } from "./hooks";
import { AccountSelect, AttentionChip, CustomerAvatar, FOCUS, ListTime, PaneEmpty, QuietPill } from "./InboxParts";
import { customerLabel } from "./labels";

const FILTERS: AttentionFilter[] = ["any", "needs_approval", "needs_human", "failed"];

/** The filter pills of the conversation list; they wrap rather than hide a filter off the edge. */
function FilterPills({ value, onChange }: { value: AttentionFilter; onChange: (next: AttentionFilter) => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t("convo.filters.label")}
      className="flex flex-wrap gap-1.5"
    >
      {FILTERS.map((name) => {
        const selected = value === name;
        return (
          <button
            key={name}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(name)}
            className={`inline-flex min-h-9 shrink-0 items-center rounded-full px-3 text-metadata font-semibold whitespace-nowrap transition-colors pointer-coarse:min-h-11 ${FOCUS} ${
              selected
                ? "bg-action text-on-action"
                : "border border-border bg-surface text-secondary hover:border-control/40 hover:bg-surface-subtle hover:text-primary"
            }`}
          >
            {t(`convo.filters.${name}`)}
          </button>
        );
      })}
    </div>
  );
}

/**
 * One conversation: who, when, the last message and why it waits. The whole row is the link;
 * its accessible name starts with the customer.
 */
function ConversationRow({ conversation, selected, to }: { conversation: Conversation; selected: boolean; to: string }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const label = customerLabel(conversation, t);
  const human = conversation.handling_mode === "human";
  return (
    <li>
      <Link
        to={to}
        data-conversation-id={conversation.id}
        aria-current={selected ? "true" : undefined}
        className={`group/row relative flex min-w-0 items-start gap-3 rounded-xl px-3 py-3 transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus ${
          selected ? "bg-assistant" : "hover:bg-surface-subtle"
        }`}
      >
        {selected ? <span aria-hidden="true" className="absolute top-3 bottom-3 left-0 w-[3px] rounded-full bg-action" /> : null}
        <CustomerAvatar label={label} selected={selected} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex min-w-0 items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5">
              <span title={label} className="min-w-0 truncate text-body leading-5 font-semibold text-primary">
                {label}
              </span>
              {conversation.is_simulated ? <SimulatedBadge compact /> : null}
            </span>
            <ListTime value={conversation.last_message_at} timeZone={workspace.timezone} />
          </span>
          <span
            className={`truncate text-body leading-5 ${
              conversation.last_message_preview ? "text-secondary" : "text-secondary italic"
            }`}
          >
            {conversation.last_message_preview ?? t("convo.noPreview")}
          </span>
          {conversation.attention !== "none" || human || conversation.window_ends_at ? (
            <span className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <AttentionChip attention={conversation.attention} />
              {human ? (
                <QuietPill>
                  <HandIcon aria-hidden="true" className="text-[0.8125rem]" />
                  {t("convo.handledByYou")}
                </QuietPill>
              ) : null}
              <WindowTimer endsAt={conversation.window_ends_at} compact />
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

interface ConversationListProps {
  activeId?: string;
  className?: string;
}

/** The Messages tab of the inbox: account and attention filters above the recent conversations. */
export function ConversationList({ activeId, className = "" }: ConversationListProps) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const rawFilter = searchParams.get("attention");
  const filter: AttentionFilter =
    rawFilter && FILTERS.includes(rawFilter as AttentionFilter) ? (rawFilter as AttentionFilter) : "any";

  const setFilter = (next: AttentionFilter) => {
    const nextParams = new URLSearchParams(searchParams);
    if (next === "any") nextParams.delete("attention");
    else nextParams.set("attention", next);
    setSearchParams(nextParams);
  };

  const conversations = useConversations(workspace.id, filter);
  const accounts = useSocialAccounts(workspace.id);
  const account = searchParams.get("account");
  const shown = conversations.data?.filter((c) => !account || c.social_account_id === account);
  const query = searchParams.toString();

  return (
    <div className={`flex min-w-0 flex-col ${className}`}>
      <h2 className="sr-only">{t("core.messages")}</h2>
      <div className="flex flex-col gap-2.5 border-b border-border px-3 pt-3 pb-3">
        {accounts.data && accounts.data.length > 1 ? (
          <AccountSelect
            accounts={accounts.data}
            value={account ?? ""}
            allLabel={t("core.allAccounts")}
            onChange={(value) => {
              const next = new URLSearchParams(searchParams);
              if (value) next.set("account", value);
              else next.delete("account");
              navigate(`/w/${workspace.id}/inbox?${next}`);
            }}
          />
        ) : null}
        <FilterPills value={filter} onChange={setFilter} />
      </div>

      <div className="flex min-w-0 flex-col p-1.5">
        {conversations.isError ? (
          <div className="p-1.5">
            <ErrorMessage error={conversations.error} />
          </div>
        ) : null}
        {conversations.isPending ? (
          <div className="px-3 py-2">
            <SkeletonRows label={t("common.loading")} rows={4} />
          </div>
        ) : null}
        {shown && shown.length === 0 ? (
          filter === "any" ? (
            <PaneEmpty icon={<ChatIcon />} title={t("convo.empty")} hint={t("convo.emptyHint")} />
          ) : (
            <PaneEmpty
              icon={<ChatIcon />}
              title={t("convo.emptyFilter", { filter: t(`convo.filters.${filter}`) })}
              hint={t("convo.emptyFilterHint")}
              action={
                <button
                  type="button"
                  onClick={() => setFilter("any")}
                  className={`inline-flex min-h-11 items-center rounded-control px-3 text-metadata font-semibold text-action underline-offset-4 hover:underline ${FOCUS}`}
                >
                  {t("convo.showAll")}
                </button>
              }
            />
          )
        ) : null}
        {shown && shown.length > 0 ? (
          <>
            <ul className="flex flex-col gap-0.5" aria-label={t("convo.title")}>
              {shown.map((conversation) => (
                <ConversationRow
                  key={conversation.id}
                  conversation={conversation}
                  selected={activeId === conversation.id}
                  to={`/w/${workspace.id}/inbox/${conversation.id}${query ? `?${query}` : ""}`}
                />
              ))}
            </ul>
            <p className="px-3 pt-2 pb-1.5 text-center text-xs text-secondary">{t("convo.recentOnly")}</p>
          </>
        ) : null}
      </div>
    </div>
  );
}
