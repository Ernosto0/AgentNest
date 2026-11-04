import { useTranslation } from "react-i18next";
import { Card } from "@/components/Card";
import { InboxIcon } from "@/components/icons";
import { ConversationList } from "./ConversationList";

export function InboxPage() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Left pane: Conversation list with filters */}
      <div className="w-full lg:w-[380px] xl:w-[420px] lg:shrink-0">
        <ConversationList />
      </div>

      {/* Right pane: Desktop placeholder when no conversation is selected */}
      <div className="hidden lg:flex flex-1 min-w-0 flex-col">
        <Card className="flex flex-col items-center justify-center p-12 text-center h-[520px] bg-surface-subtle/30 border-2 border-dashed border-border/80 rounded-2xl shadow-none">
          <div
            className="flex h-16 w-16 items-center justify-center rounded-2xl bg-surface text-action border border-border/80 shadow-xs mb-4"
            aria-hidden="true"
          >
            <InboxIcon className="text-3xl" />
          </div>
          <h2 className="text-section font-bold tracking-tight text-primary">{t("convo.selectConversation")}</h2>
          <p className="mt-2 max-w-sm text-body text-secondary">
            {t("convo.selectHint")}
          </p>
        </Card>
      </div>
    </div>
  );
}
