import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { Extraction } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SpinnerIcon } from "@/components/icons";
import { newRequestId } from "@/features/commands/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { candidatesKey } from "./hooks";

const MAX_CHARS = 8000;
const WORKING = new Set<Extraction["status"]>(["queued", "running"]);

function useStartExtraction(workspaceId: string) {
  return useMutation<Extraction, AppError, string>({
    mutationFn: (text) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/knowledge/extractions", {
          params: { path: { workspace_id: workspaceId } },
          body: { text, client_request_id: newRequestId() },
        }),
      ),
  });
}

function useExtraction(workspaceId: string, runId: string | null) {
  const queryClient = useQueryClient();
  return useQuery<Extraction, AppError>({
    queryKey: ["extraction", workspaceId, runId ?? "none"],
    enabled: runId !== null,
    queryFn: async () => {
      const run = await unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/knowledge/extractions/{run_id}", {
          params: { path: { workspace_id: workspaceId, run_id: runId ?? "" } },
        }),
      );
      if (!WORKING.has(run.status)) {
        await queryClient.invalidateQueries({ queryKey: candidatesKey(workspaceId, "pending") });
      }
      return run;
    },
    refetchInterval: (query) => (query.state.data && WORKING.has(query.state.data.status) ? 1000 : false),
  });
}

/**
 * Paste a bio or price list and get *suggestions*: the owner accepts each one (or not). The
 * text stays in the box when extraction fails, so nothing typed or pasted is lost.
 */
export function PasteExtractSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const start = useStartExtraction(workspace.id);
  const [text, setText] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const run = useExtraction(workspace.id, runId);

  const submit = async () => {
    try {
      const created = await start.mutateAsync(text.trim());
      setRunId(created.run_id);
    } catch {
      // Shown below; the text is kept.
    }
  };

  const status = run.data?.status;
  const working = start.isPending || (runId !== null && (!status || WORKING.has(status)));
  const suggestions = `/w/${workspace.id}/more/knowledge/suggestions`;

  return (
    <BottomSheet
      title={t("extract.title")}
      onClose={onClose}
      footer={
        status === "succeeded" ? (
          <div className="flex flex-wrap gap-2">
            {(run.data?.candidates_created ?? 0) > 0 ? (
              <Link
                to={suggestions}
                onClick={onClose}
                className="inline-flex min-h-11 items-center rounded-control bg-action px-4 py-2 text-sm font-medium text-on-action shadow-xs hover:bg-action-hover focus-visible:outline-2 focus-visible:outline-focus"
              >
                {t("extract.goToSuggestions")}
              </Link>
            ) : null}
            <Button
              variant="secondary"
              onClick={() => {
                setRunId(null);
                setText("");
              }}
            >
              {t("extract.again")}
            </Button>
          </div>
        ) : (
          <Button disabled={!text.trim() || working} onClick={submit}>
            {t("extract.submit")}
          </Button>
        )
      }
    >
      <div className="flex flex-col gap-3">
        <div className="rounded-panel bg-surface-subtle p-3.5 border border-border text-sm text-secondary">
          {t("extract.intro")}
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="extract-text" className="text-sm font-medium text-primary">
            {t("extract.label")}
          </label>
          <textarea
            id="extract-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={MAX_CHARS}
            rows={7}
            readOnly={working || status === "succeeded"}
            placeholder={t("extract.placeholder")}
            className="min-h-32 w-full rounded-control border border-border bg-surface p-3 text-base text-primary placeholder:text-secondary focus:border-control focus-visible:outline-2 focus-visible:outline-focus"
          />
          <span className="text-xs text-secondary">
            {t("extract.counter", { count: text.length, max: MAX_CHARS })}
          </span>
        </div>

        {working ? (
          <div role="status" className="inline-flex items-center gap-2.5 rounded-control bg-surface-subtle p-3 font-medium text-secondary border border-border">
            <SpinnerIcon className="animate-spin text-xl text-action" />
            <span className="text-sm text-primary">{t("extract.working")}</span>
          </div>
        ) : null}
        {start.error ? <ErrorMessage error={start.error} /> : null}
        {run.error ? <ErrorMessage error={run.error} /> : null}
        {status === "failed" ? (
          <div role="alert" className="rounded-panel bg-danger-subtle p-4 text-sm text-danger border border-border">
            <p className="font-semibold">{t("extract.failed")}</p>
            {run.data?.error_code ? (
              <p className="mt-1">{t(`errors.${run.data.error_code}.what`, { defaultValue: "" })}</p>
            ) : null}
          </div>
        ) : null}
        {status === "succeeded" ? (
          <div className="flex flex-col gap-2 rounded-panel bg-surface-subtle p-4 border border-border shadow-xs" data-testid="extract-result">
            <p className="font-semibold text-primary">
              {run.data && run.data.candidates_created > 0
                ? t("extract.done", { count: run.data.candidates_created })
                : t("extract.none")}
            </p>
            {run.data?.injection_suspected ? (
              <p className="text-sm text-attention font-medium">{t("extract.injection")}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </BottomSheet>
  );
}
