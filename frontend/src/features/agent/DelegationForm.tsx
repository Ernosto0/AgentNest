import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { newRequestId } from "@/features/commands/hooks";
import {
  ACTIONS,
  actionLabelKey,
  usePreviewDelegation,
  useApplyDelegation,
  type Schema,
} from "./hooks";
import { FIELD } from "./PersonalityForm";

export function DelegationForm({
  ws,
  account,
  config,
  data,
  owner,
}: {
  ws: string;
  account: string;
  config: number;
  data: Schema<"DelegationOut"> | null;
  owner: boolean;
}) {
  const { t } = useTranslation();
  const [policy, setPolicy] = useState<Schema<"DelegationPolicy">>(
    data?.policy ?? {
      actions: Object.fromEntries(
        ACTIONS.map((a) => [a, { mode: "off", sources: ["customer", "owner_task"], max_per_day: null }]),
      ),
    },
  );
  const [proposal, setProposal] = useState<Schema<"DelegationChange"> | null>(null);
  const preview = usePreviewDelegation(ws, account);
  const apply = useApplyDelegation(ws, account);
  const locked = preview.isPending || apply.isPending;

  function edit(action: string, change: Partial<Schema<"ActionRule">>) {
    setProposal(null);
    preview.reset();
    apply.reset();
    setPolicy({
      ...policy,
      actions: {
        ...policy.actions,
        [action]: { ...policy.actions[action]!, ...change },
      },
    });
  }

  return (
    <Card className="flex flex-col gap-4">
      <div className="border-b border-border pb-3">
        <h2 className="text-lg font-heading font-semibold text-primary">{t("agent.delegation")}</h2>
      </div>
      <p className="text-sm text-secondary">{t("agent.delegationHint")}</p>

      <div className="flex flex-col gap-3">
        {ACTIONS.map((action) => (
          <fieldset
            key={action}
            className="min-w-0 rounded-control border border-border bg-surface-subtle p-3.5 shadow-xs flex flex-col gap-3"
            disabled={!owner || locked}
          >
            <legend className="px-1 font-heading text-sm font-semibold text-primary">
              {t(actionLabelKey(action))}
            </legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
                <span>{t("agent.mode")}</span>
                <select
                  className={FIELD}
                  value={policy.actions[action]!.mode}
                  onChange={(e) => edit(action, { mode: e.target.value as Schema<"ActionRule">["mode"] })}
                >
                  {["automatic", "ask", "off"].map((m) => (
                    <option key={m} value={m}>
                      {t(`agent.modes.${m}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
                <span>{t("agent.dailyLimit")}</span>
                <input
                  className={FIELD}
                  type="number"
                  min={1}
                  max={10000}
                  value={policy.actions[action]!.max_per_day ?? ""}
                  onChange={(e) =>
                    edit(action, { max_per_day: e.target.value ? Number(e.target.value) : null })
                  }
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-4 pt-1">
              {(["customer", "owner_task"] as const).map((source) => (
                <label key={source} className="flex min-h-11 items-center gap-2 text-sm text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded-control border-border text-action focus-visible:outline-2 focus-visible:outline-focus"
                    checked={policy.actions[action]!.sources.includes(source)}
                    onChange={(e) =>
                      edit(action, {
                        sources: e.target.checked
                          ? [...policy.actions[action]!.sources, source]
                          : policy.actions[action]!.sources.filter((s) => s !== source),
                      })
                    }
                  />
                  <span>{t(`agent.sources.${source}`)}</span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>

      <div className="pt-2">
        {owner ? (
          <Button
            disabled={locked}
            onClick={() => {
              const body = {
                policy,
                expected_config_version: config,
                expected_delegation_version: data?.version ?? null,
                client_request_id: newRequestId(),
              };
              setProposal(null);
              preview.mutate(body, { onSuccess: () => setProposal(body) });
            }}
          >
            {t("agent.previewDelegation")}
          </Button>
        ) : (
          <p className="text-sm font-medium text-secondary">{t("agent.ownerOnly")}</p>
        )}
      </div>

      {preview.data && proposal ? (
        <div role="status" className="flex flex-col gap-3 rounded-control border border-border bg-surface-subtle p-4 shadow-xs">
          <p className="font-heading font-semibold text-primary">
            {t("agent.versionPreview", { version: preview.data.next_version })}
          </p>
          <ul className="flex flex-col gap-2 text-sm">
            {preview.data.changed_actions.map((a) => (
              <li key={a} className="rounded-control border border-border bg-surface p-3 flex flex-col gap-1">
                <span className="font-semibold text-primary">{t(actionLabelKey(a))}</span>
                <span className="text-secondary">
                  {t(`agent.modes.${data?.policy.actions[a]?.mode ?? "off"}`)} {" → "} {t(`agent.modes.${proposal.policy.actions[a]!.mode}`)}
                </span>
                <span className="text-xs text-muted">
                  {t("agent.dailyLimit")}: {data?.policy.actions[a]?.max_per_day ?? t("agent.noAdditionalLimit")} {" → "} {proposal.policy.actions[a]!.max_per_day ?? t("agent.noAdditionalLimit")}
                </span>
                <span className="text-xs text-muted">
                  {(data?.policy.actions[a]?.sources ?? ["customer", "owner_task"]).map((s) => t(`agent.sources.${s}`)).join(", ") || t("agent.noSources")}{" "}
                  {" → "}{" "}
                  {proposal.policy.actions[a]!.sources.map((s) => t(`agent.sources.${s}`)).join(", ") || t("agent.noSources")}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-sm font-medium text-attention">{t("agent.changeWarning")}</p>
          <div>
            <Button
              disabled={locked}
              onClick={() =>
                apply.mutate(proposal, {
                  onSuccess: () => {
                    setProposal(null);
                    preview.reset();
                  },
                })
              }
            >
              {t("agent.applyDelegation")}
            </Button>
          </div>
        </div>
      ) : null}

      {preview.error ? <ErrorMessage error={preview.error} /> : null}
      {apply.error ? <ErrorMessage error={apply.error} /> : null}
      {apply.isSuccess ? (
        <p role="status" className="text-sm font-medium text-success">
          {t("agent.saved")}
        </p>
      ) : null}
    </Card>
  );
}
