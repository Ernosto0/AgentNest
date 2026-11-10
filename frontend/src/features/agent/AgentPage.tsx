import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon, HomeIcon, LinkIcon, ShieldCheckIcon, SparkIcon, ChatIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS } from "./AgentParts";
import { HistoryPanel } from "./HistoryPanel";
import { useAgentDelegation, useAgentOverview, useAgentPersonality, useAgentTasks } from "./hooks";
import { OverviewPanel } from "./OverviewPanel";
import { PersonalityForm } from "./PersonalityForm";
import { DelegationForm } from "./DelegationForm";
import { TONE_DOT, TONE_PILL } from "./presentation";

const PANELS = ["overview", "voice", "permissions", "history"] as const;
type Panel = (typeof PANELS)[number];
const PANEL_ICON: Record<Panel, ReactNode> = {
  overview: <HomeIcon />,
  voice: <ChatIcon />,
  permissions: <ShieldCheckIcon />,
  history: <ClockIcon />,
};

/**
 * The assistant control centre (ui-spec §4.6). Route-aware tabs (`panel=`) and the selected
 * account (`account=`) live in the query, so links and reloads keep both.
 */
export function AgentPage() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const accounts = useSocialAccounts(workspace.id);
  const [params, setParams] = useSearchParams();
  const raw = params.get("panel");
  const panel: Panel = (PANELS as readonly string[]).includes(raw ?? "") ? (raw as Panel) : "overview";
  const account =
    accounts.data?.find((a) => a.id === params.get("account")) ?? accounts.data?.find((a) => a.status !== "disconnected");
  const href = (name: string) => {
    const next = new URLSearchParams(params);
    next.set("panel", name);
    return `?${next}`;
  };
  const picker =
    accounts.data && accounts.data.length > 1 ? (
      <label className="flex min-w-0 items-center gap-2 text-xs font-semibold text-secondary">
        <span className="shrink-0">{t("agent.account")}</span>
        <select
          className={`min-h-10 w-full min-w-0 rounded-control border border-control/50 bg-surface px-3 py-1.5 font-semibold text-primary hover:border-control sm:w-48 ${FOCUS}`}
          value={account?.id ?? ""}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            next.set("account", e.target.value);
            setParams(next);
          }}
        >
          {accounts.data.map((a) => (
            <option key={a.id} value={a.id}>
              @{a.username ?? t("agent.account")}
            </option>
          ))}
        </select>
      </label>
    ) : null;

  return (
    <div className="flex min-w-0 flex-col gap-5 pb-4">
      <header className="flex min-w-0 flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0 flex-1 basis-80">
          <h1 className="type-page break-words text-primary">{t("agent.title")}</h1>
          <p className="mt-1.5 max-w-prose text-body text-secondary">{t(`agent.intro.${panel}`)}</p>
        </div>
        <nav aria-label={t("agent.title")} className="w-full md:w-auto">
          <div className="grid grid-cols-4 gap-1 rounded-xl bg-surface-subtle p-1 ring-1 ring-border/70 ring-inset md:flex">
            {PANELS.map((name) => {
              const current = panel === name;
              return (
                <Link
                  key={name}
                  to={href(name)}
                  aria-current={current ? "page" : undefined}
                  className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-2 text-body font-semibold whitespace-nowrap transition-colors pointer-coarse:min-h-11 sm:px-3.5 ${FOCUS} ${
                    current
                      ? "bg-surface text-primary shadow-[0_1px_2px_rgb(37_59_49/0.10)] ring-1 ring-border"
                      : "text-secondary hover:bg-surface/70 hover:text-primary"
                  }`}
                >
                  <span aria-hidden="true" className={`hidden text-base sm:inline ${current ? "text-action" : ""}`}>
                    {PANEL_ICON[name]}
                  </span>
                  {t(`core.${name}`)}
                </Link>
              );
            })}
          </div>
        </nav>
      </header>

      {accounts.error ? <ErrorMessage error={accounts.error} /> : null}
      {accounts.isPending ? (
        <HeroSkeleton label={t("common.loading")} />
      ) : account ? (
        <AccountAgent key={`${workspace.id}:${account.id}:${panel}`} panel={panel} account={account} href={href} picker={picker} />
      ) : !accounts.error ? (
        <NoAccount />
      ) : null}
    </div>
  );
}

function HeroSkeleton({ label }: { label: string }) {
  return (
    <div role="status" className="flex flex-col gap-4 rounded-2xl bg-assistant p-5">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="flex items-center gap-3.5">
        <div className="size-12 rounded-full bg-surface/70 motion-safe:animate-pulse" />
        <div className="flex flex-1 flex-col gap-2">
          <div className="h-3 w-40 rounded-full bg-surface/70 motion-safe:animate-pulse" />
          <div className="h-2.5 w-64 max-w-full rounded-full bg-surface/70 motion-safe:animate-pulse" />
        </div>
      </div>
      <div aria-hidden="true" className="h-20 rounded-xl bg-surface/60 motion-safe:animate-pulse" />
    </div>
  );
}

function NoAccount() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  return (
    <section className="flex min-w-0 flex-wrap items-center gap-4 rounded-2xl bg-assistant p-5">
      <span aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-full bg-action text-xl text-on-action">
        <SparkIcon />
      </span>
      <div className="min-w-0 flex-1 basis-64">
        <h2 className="font-heading text-base font-semibold text-primary">{t("agent.empty.title")}</h2>
        <p className="text-body text-secondary">{t("agent.noAccount")}</p>
      </div>
      <Link
        to={`/w/${workspace.id}/more/settings/connections`}
        className={`inline-flex min-h-11 items-center gap-2 rounded-control bg-action px-4 text-body font-semibold text-on-action hover:bg-action-hover ${FOCUS}`}
      >
        <LinkIcon aria-hidden="true" />
        {t("agent.empty.connect")}
      </Link>
    </section>
  );
}

/** Which account the Voice, Permissions and History tabs are editing or showing. */
function AccountStrip({ account, state, simulated, picker }: { account: SocialAccount; state?: string; simulated: boolean; picker?: ReactNode }) {
  const { t } = useTranslation();
  const label = state === undefined ? null : state;
  const tone = label === "active" ? "success" : label === "paused" ? "attention" : "neutral";
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-2xl bg-assistant px-4 py-2.5">
      <div className="flex min-w-0 flex-wrap items-center gap-2.5">
        <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-full bg-action font-heading text-sm font-bold text-on-action uppercase">
          {(account.username ?? "?").slice(0, 1)}
        </span>
        <span className="min-w-0 font-heading text-body font-semibold text-primary [overflow-wrap:anywhere]">@{account.username ?? t("agent.account")}</span>
        {label ? (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 text-[11px] leading-5 font-semibold ${TONE_PILL[tone]}`}>
            <span aria-hidden="true" className={`size-1.5 rounded-full ${TONE_DOT[tone]}`} />
            {t(`agent.hero.state.${label}`)}
          </span>
        ) : null}
        {simulated ? <SimulatedBadge compact /> : null}
      </div>
      {picker}
    </div>
  );
}

function AccountAgent({
  panel,
  account,
  href,
  picker,
}: {
  panel: Panel;
  account: SocialAccount;
  href: (panel: string) => string;
  picker: ReactNode;
}) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const ws = workspace.id;
  const accountId = account.id;
  const overview = useAgentOverview(ws, accountId);
  const personality = useAgentPersonality(ws, accountId);
  const delegation = useAgentDelegation(ws, accountId);
  const tasks = useAgentTasks(ws, accountId);
  const owner = role === "owner";
  const data = overview.data;

  if (overview.error) return <ErrorMessage error={overview.error} />;
  if (!data) return <HeroSkeleton label={t("common.loading")} />;
  const state = data.controller_mode === "legacy" ? "legacy" : data.state;

  return (
    <>
      {panel === "overview" ? (
        <OverviewPanel account={account} data={data} owner={owner} tasks={tasks} policy={delegation.data?.policy} panelHref={href} picker={picker} />
      ) : (
        <AccountStrip account={account} state={state} simulated={data.is_simulated} picker={picker} />
      )}

      {panel === "voice" ? (
        <>
          {personality.data ? (
            <PersonalityForm key={`persona:${accountId}`} ws={ws} account={accountId} data={personality.data} editable={role !== "staff"} />
          ) : personality.isPending ? (
            <HeroSkeleton label={t("common.loading")} />
          ) : null}
          {personality.error ? <ErrorMessage error={personality.error} /> : null}
        </>
      ) : null}

      {panel === "permissions" ? (
        <>
          {delegation.isSuccess ? (
            <DelegationForm
              key={`policy:${data.config_version}:${delegation.data?.version ?? 0}`}
              ws={ws}
              account={accountId}
              config={data.config_version}
              data={delegation.data ?? null}
              owner={owner}
              capabilities={account.capabilities}
            />
          ) : delegation.isPending ? (
            <HeroSkeleton label={t("common.loading")} />
          ) : null}
          {delegation.error ? <ErrorMessage error={delegation.error} /> : null}
          {data.controller_mode === "legacy" ? (
            <Link className={`inline-flex min-h-11 items-center self-start rounded-control text-body font-medium text-action hover:underline ${FOCUS}`} to={`/w/${ws}/more/automation`}>
              {t("agent.legacySettings")}
            </Link>
          ) : null}
        </>
      ) : null}

      {panel === "history" ? <HistoryPanel data={data} tasks={tasks} accountId={accountId} /> : null}
    </>
  );
}
