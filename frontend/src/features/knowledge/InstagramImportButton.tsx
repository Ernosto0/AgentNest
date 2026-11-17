import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { Extraction } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SpinnerIcon } from "@/components/icons";
import { newRequestId } from "@/features/commands/hooks";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { candidatesKey } from "./hooks";

interface Props {
  variant?: "primary" | "secondary";
  onDone?: (run: Extraction) => void;
}

const workingStatuses = new Set<Extraction["status"]>(["queued", "running"]);

export function InstagramImportButton(props: Props) {
  const { workspace } = useCurrentWorkspace();
  return <InstagramImportControl key={workspace.id} workspaceId={workspace.id} {...props} />;
}

export function InstagramImportControl({ workspaceId, variant = "primary", onDone }: Props & { workspaceId: string }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const accounts = useSocialAccounts(workspaceId);
  const connected = accounts.data?.some((account) => account.status === "connected" || account.status === "degraded");
  const [runId, setRunId] = useState<string | null>(null);
  const notified = useRef<string | null>(null);
  const start = useMutation<Extraction, AppError>({
    mutationFn: () => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/knowledge/imports/instagram", {
      params: { path: { workspace_id: workspaceId } },
      body: { client_request_id: newRequestId() },
    })),
    onSuccess: (created) => setRunId(created.run_id),
  });
  const run = useQuery<Extraction, AppError>({
    queryKey: ["extraction", workspaceId, runId ?? "none"],
    enabled: runId !== null,
    queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/knowledge/extractions/{run_id}", {
      params: { path: { workspace_id: workspaceId, run_id: runId ?? "" } },
    })),
    refetchInterval: (query) => query.state.data && workingStatuses.has(query.state.data.status) ? 1000 : false,
  });

  useEffect(() => {
    const result = run.data;
    if (!result || workingStatuses.has(result.status) || notified.current === result.run_id) return;
    notified.current = result.run_id;
    if (result.status === "succeeded") {
      void client.invalidateQueries({ queryKey: candidatesKey(workspaceId, "pending") });
      void client.invalidateQueries({ queryKey: ["readiness", workspaceId] });
    }
    onDone?.(result);
  }, [run.data, client, workspaceId, onDone]);

  const working = start.isPending || (runId !== null && !run.isError && (!run.data || workingStatuses.has(run.data.status)));
  return (
    <div className="flex min-w-0 max-w-full flex-col items-start gap-2 [overflow-wrap:anywhere]">
      <Button variant={variant} disabled={!connected || working} disabledReason={!connected ? t("knowledge.importInstagram.connectFirst") : undefined}
        data-testid="open-instagram-import" className="max-w-full" onClick={() => { setRunId(null); start.mutate(); }}>
        {t("knowledge.importInstagram.button")}
      </Button>
      {working ? <p role="status" className="flex items-center gap-2 text-sm text-secondary">
        <SpinnerIcon className="shrink-0 motion-safe:animate-spin" />{t("knowledge.importInstagram.working")}
      </p> : null}
      {accounts.error ? <ErrorMessage error={accounts.error} /> : null}
      {start.error ? <ErrorMessage error={start.error} /> : null}
      {run.error ? <ErrorMessage error={run.error} /> : null}
      {run.data?.status === "succeeded" ? <p role="status" className="text-sm text-primary">
        {run.data.candidates_created > 0 ? t("knowledge.importInstagram.done", { count: run.data.candidates_created }) : t("knowledge.importInstagram.none")}
      </p> : null}
      {run.data?.status === "failed" ? <div role="alert" className="rounded-panel border border-border bg-danger-subtle p-3 text-sm text-danger">
        <p>{t("knowledge.importInstagram.failed")}</p>
        {run.data.error_code ? <p>{t(`errors.${run.data.error_code}.what`, { defaultValue: "" })}</p> : null}
      </div> : null}
      {run.data?.injection_suspected ? <p className="text-sm font-medium text-attention">{t("knowledge.importInstagram.injection")}</p> : null}
    </div>
  );
}
