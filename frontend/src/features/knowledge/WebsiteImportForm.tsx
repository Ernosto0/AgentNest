import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { Extraction } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { TextField } from "@/components/TextField";
import { SpinnerIcon } from "@/components/icons";
import { newRequestId } from "@/features/commands/hooks";
import { candidatesKey } from "./hooks";

interface Props {
  workspaceId: string;
  variant?: "primary" | "secondary";
  onDone?: (run: Extraction) => void;
}
const workingStatuses = new Set<Extraction["status"]>(["queued", "running"]);

export function WebsiteImportForm({ workspaceId, variant = "primary", onDone }: Props) {
  const { t } = useTranslation();
  const client = useQueryClient();
  // Keeping the editable value nullable lets a late prefill arrive without overwriting typing.
  const [editedUrl, setEditedUrl] = useState<string | null>(null);
  const prefill = useQuery({
    queryKey: ["website-import-prefill", workspaceId],
    queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/knowledge/imports/website/prefill", {
      params: { path: { workspace_id: workspaceId } },
    })),
    staleTime: Infinity,
  });
  const url = editedUrl ?? prefill.data?.url ?? "";
  const [runId, setRunId] = useState<string | null>(null);
  const notified = useRef<string | null>(null);
  const start = useMutation<Extraction, AppError, string>({
    mutationFn: (address) => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/knowledge/imports/website", {
      params: { path: { workspace_id: workspaceId } },
      body: { client_request_id: newRequestId(), url: address },
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
  const urlError = start.error?.status === 422 && start.error.fieldErrors.some((error) => error.field === "url");
  return <form noValidate aria-busy={working} className="flex min-w-0 max-w-full flex-col gap-2 [overflow-wrap:anywhere]" onSubmit={(event) => {
    event.preventDefault();
    if (!url.trim() || working) return;
    setRunId(null);
    start.mutate(url.trim());
  }}>
    <div className="grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
      <TextField label={t("knowledge.importWebsite.label")} type="url" inputMode="url" autoComplete="url" required maxLength={300}
        placeholder={t("knowledge.importWebsite.placeholder")} data-testid="website-import-url" value={url} disabled={working}
        error={urlError ? t("knowledge.importWebsite.invalidUrl") : undefined}
        onChange={(event) => { setEditedUrl(event.target.value); start.reset(); }} />
      <div className="flex flex-col gap-2"><Button type="submit" variant={variant} pending={working} disabled={!url.trim()}
        disabledReason={!url.trim() ? t("knowledge.importWebsite.required") : undefined}
        className="w-full sm:w-auto" data-testid="website-import-submit">{t("knowledge.importWebsite.button")}</Button></div>
    </div>
    <p className="text-metadata text-secondary">{t("knowledge.importWebsite.privacy")}</p>
    {working ? <p role="status" className="flex items-center gap-2 text-sm text-secondary"><SpinnerIcon className="shrink-0 motion-safe:animate-spin" />{t("knowledge.importWebsite.working")}</p> : null}
    {start.error && !urlError ? <ErrorMessage error={start.error} /> : null}
    {run.error ? <ErrorMessage error={run.error} /> : null}
    {run.data?.status === "succeeded" ? <p role="status" className="text-sm text-primary">{run.data.candidates_created > 0
      ? t("knowledge.importWebsite.done", { count: run.data.candidates_created }) : t("knowledge.importWebsite.none")}</p> : null}
    {run.data?.status === "failed" ? <div role="alert" className="rounded-panel border border-border bg-danger-subtle p-3 text-sm text-danger">
      <p>{t("knowledge.importWebsite.failed")}</p>
      {run.data.error_code ? <><p>{t(`errors.${run.data.error_code}.what`, { defaultValue: "" })}</p><p>{t(`errors.${run.data.error_code}.next`, { defaultValue: "" })}</p></> : null}
    </div> : null}
    {run.data?.injection_suspected ? <p className="text-sm font-medium text-attention">{t("knowledge.importWebsite.injection")}</p> : null}
  </form>;
}
