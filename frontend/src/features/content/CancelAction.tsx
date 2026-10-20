import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCancelContent } from "./hooks";
import { canCancel } from "./status";

/**
 * Cancel an item that has not gone out. Only someone with `content.approve` (owner, manager)
 * sees it: staff can edit and submit, but not cancel. A cancel is a decision, so it asks once.
 */
export function CancelAction({ item }: { item: ContentItem }) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const cancel = useCancelContent(workspace.id, item.id);
  const [asking, setAsking] = useState(false);

  if (role === "staff" || !canCancel(item.status)) return null;

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
