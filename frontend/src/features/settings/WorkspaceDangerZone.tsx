import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  useCancelWorkspaceDeletion,
  useRequestWorkspaceDeletion,
  useWorkspaceDeletionStatus,
} from "./hooks";

interface Props {
  workspaceId: string;
}

export function WorkspaceDangerZone({ workspaceId }: Props) {
  const { t } = useTranslation();
  const statusQuery = useWorkspaceDeletionStatus(workspaceId);
  const requestDeletion = useRequestWorkspaceDeletion(workspaceId);
  const cancelDeletion = useCancelWorkspaceDeletion(workspaceId);

  if (statusQuery.isPending) return null;
  const status = statusQuery.data;

  const handleRequest = () => {
    if (window.confirm(t("settings.deleteWorkspaceConfirm"))) {
      requestDeletion.mutate();
    }
  };

  const handleCancel = () => {
    cancelDeletion.mutate();
  };

  return (
    <div className="flex flex-col gap-4 rounded-panel border border-border bg-danger-subtle/30 p-5 shadow-xs">
      <div>
        <h2 className="text-base font-heading font-semibold text-danger">
          {t("settings.dangerZoneTitle")}
        </h2>
        <p className="mt-0.5 text-xs text-secondary leading-relaxed">
          {t("settings.dangerZoneDesc")}
        </p>
      </div>

      {status?.is_deleting ? (
        <div className="flex flex-col gap-3 rounded-panel border border-border bg-attention-subtle p-4 text-sm text-attention">
          <div className="font-semibold">{t("settings.deletionScheduledTitle")}</div>
          <p>
            {t("settings.deletionScheduledDesc", {
              days: status.days_remaining ?? 7,
              date: status.deletion_scheduled_at
                ? new Date(status.deletion_scheduled_at).toLocaleDateString()
                : "",
            })}
          </p>
          <div className="pt-1">
            <Button
              variant="secondary"
              disabled={cancelDeletion.isPending}
              onClick={handleCancel}
              className="border-border bg-surface text-attention hover:bg-surface-subtle"
            >
              {cancelDeletion.isPending ? t("common.loading") : t("settings.cancelDeletionBtn")}
            </Button>
          </div>
          {cancelDeletion.isError ? <ErrorMessage error={cancelDeletion.error} /> : null}
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
          <div>
            <p className="text-sm font-medium text-primary">{t("settings.deleteWorkspaceAction")}</p>
            <p className="text-xs text-secondary">{t("settings.deleteWorkspaceGraceNote")}</p>
          </div>
          <div>
            <Button
              variant="ghost"
              disabled={requestDeletion.isPending}
              onClick={handleRequest}
              className="text-danger hover:bg-danger-subtle border border-border"
            >
              {requestDeletion.isPending ? t("common.loading") : t("settings.deleteWorkspaceBtn")}
            </Button>
          </div>
        </div>
      )}

      {requestDeletion.isError ? <ErrorMessage error={requestDeletion.error} /> : null}
      {statusQuery.isError ? <ErrorMessage error={statusQuery.error} /> : null}
    </div>
  );
}
