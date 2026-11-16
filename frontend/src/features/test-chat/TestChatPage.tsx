import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Notice } from "@/components/Feedback";
import { ChevronLeftIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { TestChat } from "./TestChat";

/** The permanent "Try your assistant" screen, reached from the Assistant page (`more/agent/test`). */
export function TestChatPage() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  return (
    <div className="flex min-w-0 flex-col gap-5 pb-4">
      <header className="min-w-0">
        <Link
          to={`/w/${workspace.id}/more/agent`}
          className="inline-flex min-h-11 items-center gap-1 rounded-control text-body font-medium text-action hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <ChevronLeftIcon aria-hidden="true" />
          {t("testChat.back")}
        </Link>
        <h1 className="type-page mt-1 break-words text-primary">{t("testChat.title")}</h1>
      </header>
      {role === "staff" ? <Notice title={t("testChat.staffOnly")} tone="attention" /> : <TestChat workspace={workspace} />}
    </div>
  );
}
