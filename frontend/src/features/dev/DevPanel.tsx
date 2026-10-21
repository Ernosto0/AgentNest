import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type {
  DevJob,
  DevScript,
  FailureRule,
  HealthCheckResult,
  ResetResult,
  SimPublishedMedia,
} from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const OPERATIONS = [
  "send",
  "lookup",
  "echo",
  "profile",
  "create_container",
  "container_status",
  "publish",
  "any",
] as const;
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
    for (const name of [
      "conversations",
      "conversation",
      "approvals",
      "dev-jobs",
      "dev-rules",
      "dev-published",
      "social-accounts",
      "system-health",
    ]) {
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
  const published = useQuery<SimPublishedMedia[], AppError>({
    queryKey: ["dev-published", ws],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/dev/workspaces/{workspace_id}/simulator/published", {
            params: { path: { workspace_id: ws } },
          }),
        )
      ).items,
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
  const healthCheck = useMutation<HealthCheckResult, AppError>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/dev/workspaces/{workspace_id}/health-check", {
          params: { path: { workspace_id: ws } },
        }),
      ),
    onSettled: refresh,
  });
  const navigate = useNavigate();
  // The reset re-creates the workspace with a new id (H15): everything cached belongs to the old
  // one, so reload it all and move to the new workspace.
  const reset = useMutation<ResetResult, AppError>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/dev/workspaces/{workspace_id}/reset", {
          params: { path: { workspace_id: ws } },
        }),
      ),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries();
      void navigate(`/w/${result.workspace_id}`);
    },
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
  return { scripts, rules, jobs, published, simulate, runDue, healthCheck, reset, addRule, removeRule };
}

/** Developer tools (only when the server has DEMO_TOOLS_ENABLED): simulate customers and failures. */
export function DevPanel() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const dev = useDev(workspace.id);
  const [operation, setOperation] = useState<(typeof OPERATIONS)[number]>("send");
  const [mode, setMode] = useState<(typeof MODES)[number]>("transient");
  const [confirmReset, setConfirmReset] = useState(false);

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

      <Card className="flex flex-col gap-3" data-testid="sim-published">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{t("devPanel.published")}</h2>
          <Button
            variant="ghost"
            disabled={dev.published.isFetching}
            onClick={() => void dev.published.refetch()}
          >
            {t("devPanel.refresh")}
          </Button>
        </div>
        <p className="text-sm text-slate-600">{t("devPanel.publishedHint")}</p>
        {dev.published.error ? <ErrorMessage error={dev.published.error} /> : null}
        {dev.published.data && dev.published.data.length === 0 ? (
          <p className="text-sm">{t("devPanel.publishedNone")}</p>
        ) : null}
        <ul className="flex flex-col gap-2 text-sm">
          {(dev.published.data ?? []).map((media) => (
            <li key={media.media_id} data-testid="sim-published-item" className="flex flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium">
                  {t("devPanel.publishedRow", {
                    type: media.media_type,
                    time: new Date(media.published_at).toLocaleString(i18n.language, {
                      dateStyle: "short",
                      timeStyle: "medium",
                      timeZone: workspace.timezone,
                    }),
                  })}
                </span>
                {media.is_simulated ? <SimulatedBadge /> : null}
              </span>
              <span className="break-words text-slate-700">{media.caption ?? t("devPanel.noCaption")}</span>
              <span className="break-all text-xs text-slate-600">
                {media.media_id} · {media.permalink}
              </span>
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
        <div className="flex flex-col gap-2 border-t border-slate-200 pt-3">
          <p className="text-sm text-slate-600">{t("devPanel.healthCheckHint")}</p>
          <div>
            <Button variant="secondary" disabled={dev.healthCheck.isPending} onClick={() => dev.healthCheck.mutate()}>
              {t("devPanel.healthCheck")}
            </Button>
          </div>
          {dev.healthCheck.data ? (
            <p role="status" data-testid="health-check-result" className="text-sm">
              {t("devPanel.healthCheckResult", {
                checked: dev.healthCheck.data.checked,
                recovered: dev.healthCheck.data.recovered,
              })}
            </p>
          ) : null}
          {dev.healthCheck.error ? <ErrorMessage error={dev.healthCheck.error} /> : null}
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

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">{t("devPanel.reset.title")}</h2>
        <p className="text-sm text-slate-600">{t("devPanel.reset.hint")}</p>
        <div>
          <Button variant="danger" data-testid="dev-reset" onClick={() => setConfirmReset(true)}>
            {t("devPanel.reset.button")}
          </Button>
        </div>
      </Card>

      {confirmReset ? (
        <BottomSheet
          title={t("devPanel.reset.confirmTitle")}
          onClose={() => setConfirmReset(false)}
          footer={
            <div className="flex flex-wrap gap-2">
              <Button
                variant="danger"
                data-testid="dev-reset-confirm"
                disabled={dev.reset.isPending}
                onClick={() => dev.reset.mutate(undefined, { onSuccess: () => setConfirmReset(false) })}
              >
                {t("devPanel.reset.confirm")}
              </Button>
              <Button variant="secondary" onClick={() => setConfirmReset(false)}>
                {t("common.cancel")}
              </Button>
            </div>
          }
        >
          <p>{t("devPanel.reset.confirmBody")}</p>
          {dev.reset.error ? <ErrorMessage error={dev.reset.error} /> : null}
        </BottomSheet>
      ) : null}
    </div>
  );
}
