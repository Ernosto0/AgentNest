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
                className="inline-flex min-h-11 items-center rounded-lg bg-indigo-700 px-4 font-medium text-white"
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
        <p className="text-sm text-slate-700">{t("extract.intro")}</p>
        <div className="flex flex-col gap-1">
          <label htmlFor="extract-text" className="text-sm font-medium">
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
            className="min-h-32 w-full rounded-lg border border-slate-300 bg-white p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600"
          />
          <span className="text-xs text-slate-600">
            {t("extract.counter", { count: text.length, max: MAX_CHARS })}
          </span>
        </div>

        {working ? (
          <p role="status" className="inline-flex items-center gap-2 font-medium text-slate-700">
            <SpinnerIcon className="animate-spin text-xl" />
            {t("extract.working")}
          </p>
        ) : null}
        {start.error ? <ErrorMessage error={start.error} /> : null}
        {run.error ? <ErrorMessage error={run.error} /> : null}
        {status === "failed" ? (
          <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
            <p className="font-medium">{t("extract.failed")}</p>
            {run.data?.error_code ? (
              <p>{t(`errors.${run.data.error_code}.what`, { defaultValue: "" })}</p>
            ) : null}
          </div>
        ) : null}
        {status === "succeeded" ? (
          <div className="flex flex-col gap-2" data-testid="extract-result">
            <p className="font-medium">
              {run.data && run.data.candidates_created > 0
                ? t("extract.done", { count: run.data.candidates_created })
                : t("extract.none")}
            </p>
            {run.data?.injection_suspected ? (
              <p className="text-sm text-slate-700">{t("extract.injection")}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </BottomSheet>
  );
}
