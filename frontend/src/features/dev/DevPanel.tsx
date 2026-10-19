import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { DevJob, DevScript, FailureRule } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const OPERATIONS = ["send", "lookup", "echo", "profile", "any"] as const;
const MODES = [
  "transient",
  "rate_limited",
  "auth_revoked",
  "permission_missing",
  "window_closed",
  "invalid_media",
  "timeout_after_success",
] as const;

function useDev(ws: string) {
  const queryClient = useQueryClient();
  const refresh = () => {
    for (const name of ["conversations", "conversation", "approvals", "dev-jobs", "dev-rules"]) {
      void queryClient.invalidateQueries({ queryKey: [name] });
    }
  };
  const scripts = useQuery<DevScript[], AppError>({
    queryKey: ["dev-scripts"],
    queryFn: () => unwrap(api.GET("/api/v1/dev/scripts")),
  });
  const rules = useQuery<FailureRule[], AppError>({
    queryKey: ["dev-rules", ws],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/dev/workspaces/{workspace_id}/failure-rules", {
            params: { path: { workspace_id: ws } },
          }),
        )
      ).items,
  });
  const jobs = useQuery<DevJob[], AppError>({
    queryKey: ["dev-jobs", ws],
    queryFn: async () => (await unwrap(api.GET("/api/v1/dev/jobs", { params: { query: {} } }))).items,
    refetchInterval: 5000,
  });
  const simulate = useMutation<unknown, AppError, string>({
    mutationFn: (scriptId) =>
      unwrap(
        api.POST("/api/v1/dev/workspaces/{workspace_id}/simulate/customer-message", {
          params: { path: { workspace_id: ws } },
          body: { script_id: scriptId },
        }),
      ),
    onSettled: refresh,
  });
  const runDue = useMutation<{ ran: number }, AppError>({
    mutationFn: () => unwrap(api.POST("/api/v1/dev/jobs/run-due")),
    onSettled: refresh,
  });
  const addRule = useMutation<unknown, AppError, { operation: string; mode: string; remaining: number | null }>({
    mutationFn: ({ operation, mode, remaining }) =>
      unwrap(
        api.POST("/api/v1/dev/workspaces/{workspace_id}/failure-rules", {
          params: { path: { workspace_id: ws } },
          body: { operation, mode, remaining } as never,
        }),
      ),
    onSettled: refresh,
  });
  const removeRule = useMutation<unknown, AppError, string>({
    mutationFn: (ruleId) =>
      unwrap(
        api.DELETE("/api/v1/dev/workspaces/{workspace_id}/failure-rules/{rule_id}", {
          params: { path: { workspace_id: ws, rule_id: ruleId } },
        }),
      ),
    onSettled: refresh,
  });
  return { scripts, rules, jobs, simulate, runDue, addRule, removeRule };
}

/** Developer tools (only when the server has DEMO_TOOLS_ENABLED): simulate customers and failures. */
export function DevPanel() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const dev = useDev(workspace.id);
  const [operation, setOperation] = useState<(typeof OPERATIONS)[number]>("send");
  const [mode, setMode] = useState<(typeof MODES)[number]>("transient");

  return (
    <div className="flex flex-col gap-5" data-testid="dev-panel">
      <h1 className="text-2xl font-semibold">{t("devPanel.title")}</h1>
      <p className="text-slate-600">{t("devPanel.intro")}</p>

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">{t("devPanel.customers")}</h2>
        <ul className="flex flex-col gap-2">
          {(dev.scripts.data ?? []).map((script) => (
            <li key={script.id} className="flex flex-wrap items-center justify-between gap-2">
              <span className="min-w-0">
                <span className="block font-medium">
                  {script.label[i18n.language] ?? script.label.tr ?? script.id}
                </span>
                <span className="block text-sm break-words text-slate-600">
                  {script.customer_alias}: {script.text ?? t("devPanel.photoOnly")}
                </span>
              </span>
              <Button
                variant="secondary"
                data-script={script.id}
                disabled={dev.simulate.isPending}
                onClick={() => dev.simulate.mutate(script.id)}
              >
                {t("devPanel.send")}
              </Button>
            </li>
          ))}
        </ul>
        {dev.simulate.error ? <ErrorMessage error={dev.simulate.error} /> : null}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">{t("devPanel.failures")}</h2>
        <div className="flex flex-wrap gap-2">
          <select
            aria-label={t("devPanel.operation")}
            value={operation}
            onChange={(event) => setOperation(event.target.value as (typeof OPERATIONS)[number])}
            className="min-h-11 rounded-lg border border-slate-300 bg-white px-3"
          >
            {OPERATIONS.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
          <select
            aria-label={t("devPanel.mode")}
            value={mode}
            onChange={(event) => setMode(event.target.value as (typeof MODES)[number])}
            className="min-h-11 rounded-lg border border-slate-300 bg-white px-3"
          >
            {MODES.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
          <Button
            variant="secondary"
            disabled={dev.addRule.isPending}
            onClick={() => dev.addRule.mutate({ operation, mode, remaining: 1 })}
          >
            {t("devPanel.addRule")}
          </Button>
        </div>
        <ul>
          {(dev.rules.data ?? []).map((rule) => (
            <li key={rule.id} className="flex items-center justify-between gap-2">
              <span>
                {rule.operation} → {rule.mode} ({rule.remaining ?? "∞"})
              </span>
              <Button variant="ghost" onClick={() => dev.removeRule.mutate(rule.id)}>
                {t("devPanel.removeRule")}
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">{t("devPanel.jobs")}</h2>
        <div>
          <Button variant="secondary" disabled={dev.runDue.isPending} onClick={() => dev.runDue.mutate()}>
            {t("devPanel.runDue")}
          </Button>
        </div>
        <ul className="text-sm">
          {(dev.jobs.data ?? []).slice(0, 12).map((job) => (
            <li key={job.id}>
              {job.job_type} · {job.status}
              {job.last_error_code ? ` · ${job.last_error_code}` : ""}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
