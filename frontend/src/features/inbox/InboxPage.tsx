import { useTranslation } from "react-i18next";
import { Card } from "@/components/Card";
import { InboxIcon } from "@/components/icons";
import { ConversationList } from "./ConversationList";

export function InboxPage() {
  const { t } = useTranslation();

  return (
    <div className="grid min-w-0 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      {/* Left pane: Conversation list with filters */}
      <div className="min-w-0">
        <ConversationList />
      </div>

      {/* Right pane: Desktop placeholder when no conversation is selected */}
      <div className="hidden min-w-0 flex-col pt-28 lg:flex">
        <Card className="flex flex-col items-start justify-center gap-2 p-5 bg-surface-subtle border-0 shadow-none">
          <div
            className="mb-2 flex h-11 w-11 items-center justify-center rounded-control bg-surface text-action border border-border"
            aria-hidden="true"
          >
            <InboxIcon className="text-xl" />
          </div>
          <h2 className="text-section font-bold tracking-tight text-primary">{t("convo.selectConversation")}</h2>
          <p className="text-body text-secondary">
            {t("convo.selectHint")}
          </p>
        </Card>
      </div>
    </div>
  );
}
