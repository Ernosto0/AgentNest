import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { Workspace } from "@/api/types";
import { Button } from "@/components/Button";
import { Notice } from "@/components/Feedback";
import { TestChat } from "@/features/test-chat/TestChat";
import { useTestChat } from "@/features/test-chat/hooks";

/**
 * A skippable wizard step: the workspace now exists, so the owner can try the assistant
 * before adding business details. Skipping or continuing both go on to website import.
 */
export function WizardTryStep({ workspace, onDone }: { workspace: Workspace; onDone: () => void }) {
  const { t } = useTranslation();
  const heading = useRef<HTMLHeadingElement>(null);
  const chat = useTestChat(workspace.id);
  const tried = (chat.data?.items.length ?? 0) > 0;
  useEffect(() => { heading.current?.focus(); }, []);
  return (
    <section className="flex flex-col gap-5 rounded-panel border border-border bg-surface p-5 sm:p-6" aria-labelledby="wizard-try-heading">
      <div>
        <h2 id="wizard-try-heading" ref={heading} tabIndex={-1} className="type-section rounded-control focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{t("testChat.title")}</h2>
        <p className="mt-1 text-body text-secondary">{t("testChat.wizard.intro")}</p>
      </div>
      <Notice title={t("testChat.wizard.noKnowledge")} tone="attention" />
      <TestChat workspace={workspace} />
      <Button variant={tried ? "primary" : "secondary"} block onClick={onDone}>{tried ? t("testChat.wizard.continue") : t("testChat.wizard.skip")}</Button>
    </section>
  );
}
