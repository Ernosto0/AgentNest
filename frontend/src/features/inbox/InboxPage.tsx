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
        <Card className="flex flex-col items-center justify-center p-12 text-center h-[520px] bg-slate-50/50 border-dashed border-2 border-slate-200">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-slate-400 mb-4" aria-hidden="true">
            <InboxIcon className="text-3xl" />
          </div>
          <h2 className="text-lg font-semibold text-slate-900">{t("convo.selectConversation")}</h2>
          <p className="mt-1 max-w-sm text-sm text-slate-500">
            {t("convo.selectHint")}
          </p>
        </Card>
      </div>
    </div>
  );
}
