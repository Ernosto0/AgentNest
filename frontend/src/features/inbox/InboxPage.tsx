import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
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

/** Conversations that need you first; every row says why and how long you have to answer. */
export function InboxPage() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [filter, setFilter] = useState<AttentionFilter>("any");
  const conversations = useConversations(workspace.id, filter);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("convo.title")}</h1>
        <p className="mt-1 text-slate-600">{t("convo.intro")}</p>
      </div>

      <div role="tablist" aria-label={t("convo.filters.label")} className="flex flex-wrap gap-2">
        {FILTERS.map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={filter === name}
            onClick={() => setFilter(name)}
            className={`min-h-11 rounded-lg px-4 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600 ${
              filter === name ? "bg-indigo-700 text-white" : "bg-white text-slate-800 ring-1 ring-slate-300"
            }`}
          >
            {t(`convo.filters.${name}`)}
          </button>
        ))}
      </div>

      {conversations.isError ? <ErrorMessage error={conversations.error} /> : null}
      {conversations.isPending ? <p>{t("common.loading")}</p> : null}
      {conversations.data && conversations.data.length === 0 ? (
        <EmptyState title={t("convo.empty")} description={t("convo.emptyHint")} />
      ) : null}
      {conversations.data && conversations.data.length > 0 ? (
        <Card className="p-0">
          <ul className="flex flex-col gap-3 p-3" aria-label={t("convo.title")}>
            {conversations.data.map((conversation) => (
              <li key={conversation.id}>
                <Link
                  to={`/w/${workspace.id}/inbox/${conversation.id}`}
                  data-conversation-id={conversation.id}
                  className="flex min-h-16 items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 ring-1 ring-slate-200 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                >
                  <span className="min-w-0">
                    <span className="block font-medium">{customerLabel(conversation, t)}</span>
                    <span className="block truncate text-sm text-slate-600">
                      {conversation.last_message_preview ?? t("convo.noPreview")}
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                      {conversation.attention !== "none" ? (
                        <span
                          data-testid="attention-chip"
                          className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-900"
                        >
                          {t(`convo.attention.${conversation.attention}`)}
                        </span>
                      ) : null}
                      {conversation.handling_mode === "human" ? (
                        <span className="text-slate-700">{t("convo.handledByYou")}</span>
                      ) : null}
                      <WindowTimer endsAt={conversation.window_ends_at} />
                      {conversation.is_simulated ? <SimulatedBadge /> : null}
                    </span>
                  </span>
                  <ChevronRightIcon className="shrink-0 text-xl text-slate-400" />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
