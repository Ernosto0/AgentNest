import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { AppError } from "@/api/errors";
import { AppShell } from "@/app/layout/AppShell";
import { NotFoundPage } from "@/app/NotFoundPage";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { FullScreenStatus } from "@/components/FullScreenStatus";
import { useMe } from "@/features/auth/hooks";
import { CurrentWorkspaceContext } from "./context";
import { useWorkspace } from "./hooks";

/**
 * Workspace guard for /w/:workspaceId. A workspace the user is not a member of answers 404,
 * which is shown as "not found", exactly like a workspace that does not exist.
 */
export function WorkspaceGate() {
  const { t } = useTranslation();
  const { workspaceId = "" } = useParams();
  const me = useMe();
  const workspace = useWorkspace(workspaceId);

  if (workspace.isPending) return <FullScreenStatus>{t("common.loading")}</FullScreenStatus>;
  if (workspace.isError) {
    if (workspace.error instanceof AppError && workspace.error.status === 404) {
      return <NotFoundPage />;
    }
    return (
      <FullScreenStatus>
        <ErrorMessage error={workspace.error} />
        <Button onClick={() => void workspace.refetch()}>{t("common.retry")}</Button>
      </FullScreenStatus>
    );
  }

  const membership = me.data?.memberships.find((m) => m.workspace_id === workspace.data.id);
  if (!membership) return <NotFoundPage />;

  return (
    <CurrentWorkspaceContext.Provider value={{ workspace: workspace.data, role: membership.role }}>
      <AppShell />
    </CurrentWorkspaceContext.Provider>
  );
}
