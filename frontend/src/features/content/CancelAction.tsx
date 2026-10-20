import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
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
      <Button variant="secondary" onClick={() => setAsking(true)}>
        {t("content.actions.cancel")}
      </Button>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-slate-50 p-3" data-testid="cancel-confirm">
      <p className="text-sm">{t("content.actions.cancelAsk")}</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate(undefined)}>
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
