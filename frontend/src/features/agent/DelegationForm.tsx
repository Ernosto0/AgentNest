import { useDirtyForm } from "@/components/DirtyForms";
import { useState, type ComponentType, type SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CalendarIcon, ChatIcon, CheckIcon, ChevronRightIcon, CommentIcon, HandIcon, ImageIcon, InfoIcon, SparkIcon, XIcon } from "@/components/icons";
import { newRequestId } from "@/features/commands/hooks";
import { useCalendarConnections } from "@/features/settings/hooks";
import { FOCUS, ModeChip, Segmented } from "./AgentParts";
import { ACTIONS, actionLabelKey, usePreviewDelegation, useApplyDelegation, type Schema } from "./hooks";
import { FIELD } from "./PersonalityForm";
import { ACTION_CAPABILITY, type Mode } from "./presentation";

type Rule = Schema<"ActionRule">;
const MODES: Mode[] = ["off", "ask", "automatic"];
const SOURCES = ["customer", "owner_task"] as const;
const GROUPS: { key: string; icon: ComponentType<SVGProps<SVGSVGElement>>; prefix: string }[] = [
  { key: "messaging", icon: ChatIcon, prefix: "dm." },
  { key: "comments", icon: CommentIcon, prefix: "comment." },
  { key: "content", icon: ImageIcon, prefix: "content." },
  { key: "calendar", icon: CalendarIcon, prefix: "calendar." },
];
const MODE_ICON = { off: XIcon, ask: HandIcon, automatic: SparkIcon } as const;

const blank = (): Schema<"DelegationPolicy"> => ({
  actions: Object.fromEntries(ACTIONS.map((a) => [a, { mode: "off", sources: ["customer", "owner_task"], max_per_day: null }])),
});
const same = (a: Rule | undefined, b: Rule | undefined) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/**
 * Per-action delegation (ui-spec §4.6). Every action keeps its own off/ask/automatic mode; limits and
 * request sources stay under "Advanced settings". Nothing applies before a successful preview of the
 * exact policy, and applying sends exactly what was previewed.
 */
export function DelegationForm({
  ws,
  account,
  config,
  data,
  owner,
  capabilities = {},
}: {
  ws: string;
  account: string;
  config: number;
  data: Schema<"DelegationOut"> | null;
  owner: boolean;
  capabilities?: Record<string, unknown>;
}) {
  const { t } = useTranslation();
  const initial = data?.policy ?? blank();
  const [policy, setPolicy] = useState<Schema<"DelegationPolicy">>(data?.policy ?? blank());
  const [proposal, setProposal] = useState<Schema<"DelegationChange"> | null>(null);
  const preview = usePreviewDelegation(ws, account);
  const apply = useApplyDelegation(ws, account);
  const calendars = useCalendarConnections(ws);
  const calendarConnected = (calendars.data ?? []).some((c) => c.status !== "disconnected" && !c.disconnected_at);
  useDirtyForm(!apply.isSuccess && JSON.stringify(policy) !== JSON.stringify(initial));
  const locked = preview.isPending || apply.isPending;
  const changed = ACTIONS.filter((a) => !same(policy.actions[a], initial.actions[a]));

  function edit(action: string, change: Partial<Rule>) {
    setProposal(null);
    preview.reset();
    apply.reset();
    setPolicy({ ...policy, actions: { ...policy.actions, [action]: { ...policy.actions[action]!, ...change } } });
  }

  /** Why an action cannot work on this account even if allowed (explains; the server still decides). */
  const unavailable = (action: string): string | null => {
    const needed = ACTION_CAPABILITY[action];
    if (needed && capabilities[needed] !== true) return t("agent.permissions.needsCapability");
    if (action.startsWith("calendar.") && calendars.isSuccess && !calendarConnected) return t("agent.permissions.needsCalendar");
    return null;
  };

  return (
    <div className="flex min-w-0 flex-col gap-4 lg:gap-5">
      <section aria-labelledby="agent-delegation-title" className="flex min-w-0 flex-col gap-4 rounded-2xl border border-border bg-surface p-4 sm:p-5">
        <div className="flex min-w-0 items-start gap-3">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-subtle text-base text-action">
            <HandIcon />
          </span>
          <div className="min-w-0">
            <h2 id="agent-delegation-title" className="font-heading text-base font-semibold tracking-tight text-primary">{t("agent.delegation")}</h2>
            <p className="text-metadata text-secondary">{t("agent.delegationHint")}</p>
          </div>
        </div>
        <ul className="grid gap-2 sm:grid-cols-3" aria-label={t("agent.permissions.legendLabel")}>
          {MODES.map((mode) => {
            const Icon = MODE_ICON[mode];
            return (
              <li key={mode} className="flex min-w-0 items-start gap-2.5 rounded-xl bg-surface-subtle/70 px-3 py-2.5">
                <Icon aria-hidden="true" className="mt-0.5 shrink-0 text-action" />
                <div className="min-w-0">
                  <p className="text-metadata font-semibold text-primary">{t(`agent.modes.${mode}`)}</p>
                  <p className="text-xs leading-snug text-secondary">{t(`agent.permissions.legend.${mode}`)}</p>
                </div>
              </li>
            );
          })}
        </ul>
        {!owner ? (
          <p className="flex items-start gap-2 rounded-xl bg-info-subtle px-3.5 py-2.5 text-metadata text-info">
            <InfoIcon aria-hidden="true" className="mt-0.5 shrink-0" />
            {t("agent.ownerOnly")}
          </p>
        ) : null}
      </section>

      <div className="min-w-0 gap-5 min-[1400px]:columns-2">
        {GROUPS.map((group) => {
          const Icon = group.icon;
          const actions = ACTIONS.filter((a) => a.startsWith(group.prefix));
          return (
            <section key={group.key} aria-labelledby={`perm-${group.key}`} className="mb-4 flex min-w-0 break-inside-avoid flex-col rounded-2xl border border-border bg-surface last:mb-0 lg:mb-5">
              <div className="flex items-center gap-2.5 border-b border-border px-4 py-3 sm:px-5">
                <Icon aria-hidden="true" className="shrink-0 text-base text-action" />
                <h3 id={`perm-${group.key}`} className="font-heading text-body font-semibold text-primary">{t(`core.${group.key}`)}</h3>
                <span className="ml-auto flex flex-wrap justify-end gap-1">
                  {MODES.filter((m) => actions.some((a) => policy.actions[a]?.mode === m)).map((m) => (
                    <ModeChip key={m} mode={m} />
                  ))}
                </span>
              </div>
              <div className="flex flex-col divide-y divide-border/70">
                {actions.map((action) => {
                  const rule = policy.actions[action]!;
                  const problem = unavailable(action);
                  const dirty = changed.includes(action);
                  return (
                    <fieldset key={action} disabled={!owner || locked} className="min-w-0 px-4 py-3.5 sm:px-5">
                      <legend className="sr-only">{t(actionLabelKey(action))}</legend>
                      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2">
                        <div className="min-w-0 flex-1 basis-48">
                          <p aria-hidden="true" className="flex flex-wrap items-center gap-2 text-body font-medium text-primary">
                            {t(actionLabelKey(action))}
                            {dirty ? (
                              <span className="rounded-full bg-info-subtle px-1.5 text-[11px] leading-5 font-semibold text-info">{t("agent.permissions.changed")}</span>
                            ) : null}
                          </p>
                          {problem ? (
                            <p className={`flex items-start gap-1.5 text-xs ${rule.mode === "off" ? "text-secondary" : "font-medium text-attention"}`}>
                              <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
                              {problem}
                            </p>
                          ) : null}
                        </div>
                        <Segmented
                          label={t("agent.mode")}
                          hideLabel
                          value={rule.mode}
                          options={MODES.map((m) => ({ value: m, label: t(`agent.modes.${m}`) }))}
                          onChange={(mode) => edit(action, { mode })}
                          className="w-full sm:w-auto"
                          stretch
                        />
                      </div>
                      <details className="group mt-1">
                        <summary className={`-mx-1 flex min-h-9 cursor-pointer list-none items-start gap-1.5 rounded-control px-1 py-2 text-xs text-secondary hover:text-primary pointer-coarse:min-h-11 ${FOCUS}`}>
                          <ChevronRightIcon aria-hidden="true" className="mt-0.5 shrink-0 transition-transform group-open:rotate-90" />
                          <span className="min-w-0">
                            <span className="font-semibold">{t("core.advanced")}</span>
                            <span className="hidden sm:inline">
                              {" · "}
                              {rule.max_per_day ? t("agent.permissions.limitShort", { count: rule.max_per_day }) : t("agent.noAdditionalLimit")}
                              {" · "}
                              {rule.sources.length ? rule.sources.map((s) => t(`agent.sources.${s}`)).join(", ") : t("agent.noSources")}
                            </span>
                          </span>
                        </summary>
                        <div className="mt-2 grid gap-3 rounded-xl bg-surface-subtle/70 p-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
                          <label className="flex flex-col gap-1.5 text-xs font-semibold text-primary">
                            <span>{t("agent.dailyLimit")}</span>
                            <input
                              className={FIELD}
                              type="number"
                              min={1}
                              max={10000}
                              value={rule.max_per_day ?? ""}
                              onChange={(e) => edit(action, { max_per_day: e.target.value ? Number(e.target.value) : null })}
                            />
                          </label>
                          <fieldset className="flex min-w-0 flex-col gap-1.5">
                            <legend className="mb-1.5 text-xs font-semibold text-primary">{t("agent.permissions.sources")}</legend>
                            <div className="flex flex-wrap gap-2">
                              {SOURCES.map((source) => (
                                <label
                                  key={source}
                                  className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-control border border-border bg-surface px-3 py-1.5 text-metadata text-primary transition-colors select-none hover:border-control"
                                >
                                  <input
                                    type="checkbox"
                                    className="size-4 rounded-control accent-action focus-visible:outline-2 focus-visible:outline-focus"
                                    checked={rule.sources.includes(source)}
                                    onChange={(e) =>
                                      edit(action, {
                                        sources: e.target.checked ? [...rule.sources, source] : rule.sources.filter((s) => s !== source),
                                      })
                                    }
                                  />
                                  <span>{t(`agent.sources.${source}`)}</span>
                                </label>
                              ))}
                            </div>
                          </fieldset>
                        </div>
                      </details>
                    </fieldset>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>

      {owner ? (
        <div
          className={`z-10 flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-2xl border px-4 py-3 sm:px-5 ${
            changed.length && !proposal
              ? "sticky bottom-[calc(4.75rem+env(safe-area-inset-bottom))] border-action/30 bg-surface/95 shadow-[0_8px_24px_rgb(18_31_24/0.10)] backdrop-blur md:bottom-4"
              : "border-border bg-surface"
          }`}
        >
          <p className="text-metadata text-secondary" role="status">
            {changed.length ? t("agent.permissions.pending", { count: changed.length }) : t("agent.permissions.noChanges")}
          </p>
          <Button
            pending={preview.isPending}
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
        </div>
      ) : null}

      {preview.data && proposal ? (
        <section role="status" aria-labelledby="agent-delegation-preview" className="flex flex-col gap-3 rounded-2xl bg-assistant p-4 sm:p-5">
          <h3 id="agent-delegation-preview" className="font-heading text-base font-semibold text-primary">
            {t("agent.versionPreview", { version: preview.data.next_version })}
          </h3>
          {preview.data.changed_actions.length === 0 ? (
            <p className="text-metadata text-secondary">{t("agent.permissions.previewNone")}</p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {preview.data.changed_actions.map((a) => {
                const before = data?.policy.actions[a];
                const after = proposal.policy.actions[a]!;
                return (
                  <li key={a} className="flex min-w-0 flex-col gap-1.5 rounded-xl bg-surface px-3.5 py-3">
                    <span className="text-body font-semibold text-primary">{t(actionLabelKey(a))}</span>
                    <span className="flex flex-wrap items-center gap-1.5 text-metadata">
                      <ModeChip mode={before?.mode ?? "off"} />
                      <span className="text-secondary">→</span>
                      <ModeChip mode={after.mode} />
                    </span>
                    <span className="text-xs text-secondary">
                      {t("agent.dailyLimit")}: {before?.max_per_day ?? t("agent.noAdditionalLimit")} {" → "} {after.max_per_day ?? t("agent.noAdditionalLimit")}
                    </span>
                    <span className="text-xs text-secondary">
                      {(before?.sources ?? ["customer", "owner_task"]).map((s) => t(`agent.sources.${s}`)).join(", ") || t("agent.noSources")}
                      {" → "}
                      {after.sources.map((s) => t(`agent.sources.${s}`)).join(", ") || t("agent.noSources")}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="flex items-start gap-2 rounded-xl bg-attention-subtle px-3.5 py-2.5 text-metadata font-medium text-attention">
            <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
            {t("agent.changeWarning")}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              pending={apply.isPending}
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
            <Button
              variant="ghost"
              disabled={locked}
              onClick={() => {
                setProposal(null);
                preview.reset();
              }}
            >
              {t("agent.permissions.keepEditing")}
            </Button>
          </div>
        </section>
      ) : null}

      {preview.error ? <ErrorMessage error={preview.error} /> : null}
      {apply.error ? <ErrorMessage error={apply.error} /> : null}
      {apply.isSuccess ? (
        <p role="status" className="inline-flex items-center gap-2 self-start rounded-xl bg-success-subtle px-3.5 py-2.5 text-metadata font-semibold text-success">
          <CheckIcon aria-hidden="true" />
          {t("agent.saved")}
        </p>
      ) : null}
    </div>
  );
}
