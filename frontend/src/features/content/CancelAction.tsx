import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCancelContent } from "./hooks";

/**
 * Cancel an item that has not gone out. The server says whether this viewer may (`can_cancel`):
 * owners and managers for any cancellable item, staff only for their own pending submission
 * (withdrawing it). A cancel is a decision, so it asks once.
 */
export function CancelAction({ item }: { item: ContentItem }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const cancel = useCancelContent(workspace.id, item.id);
  const [asking, setAsking] = useState(false);

  if (!item.can_cancel) return null;

  if (!asking) {
    return (
      <Button variant="secondary" onClick={() => setAsking(true)} className="shadow-xs">
        {t("content.actions.cancel")}
      </Button>
    );
  }
  return (
    <div
      className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-4 shadow-sm"
      data-testid="cancel-confirm"
    >
      <div className="flex items-center gap-2 text-danger">
        <AlertIcon className="text-base shrink-0" />
        <p className="text-sm font-semibold text-primary">{t("content.actions.cancelAsk")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate(undefined)} className="shadow-xs">
          {cancel.isPending ? t("content.actions.cancelling") : t("content.actions.cancelConfirm")}
        </Button>
        <Button variant="ghost" disabled={cancel.isPending} onClick={() => setAsking(false)}>
          {t("content.actions.cancelKeep")}
        </Button>
      </div>
      {cancel.error ? <ErrorMessage error={cancel.error} /> : null}
    </div>
  );
}
