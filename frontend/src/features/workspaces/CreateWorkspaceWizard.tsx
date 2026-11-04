import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useBlocker, useNavigate } from "react-router-dom";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { Workspace, WorkspaceCreateBody } from "@/api/types";
import { PublicShell } from "@/app/layout/PublicShell";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice } from "@/components/Feedback";
import { ChoiceField, SelectField } from "@/components/FormFields";
import { TextField } from "@/components/TextField";
import { meKey } from "@/features/auth/hooks";
import { CURRENCIES, browserTimezone, defaultsForMarket, timezoneOptions, type Market } from "./wizardDefaults";

const CATEGORIES = ["beauty_wellness", "food_beverage", "retail", "fitness", "health_clinic", "education", "hospitality", "services", "other"] as const;
const STEPS = ["name", "category", "locale"] as const;

function useCreateWorkspace() {
  const client = useQueryClient();
  return useMutation<Workspace, AppError, WorkspaceCreateBody>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/workspaces", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: meKey }),
  });
}

/** Three existing steps; market changes reapply documented defaults, Back retains overrides. */
export function CreateWorkspaceWizard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateWorkspace();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [category, setCategory] = useState<(typeof CATEGORIES)[number] | null>(null);
  const [market, setMarket] = useState<Market>("tr");
  const [initialSettings] = useState(() => defaultsForMarket("tr", browserTimezone()));
  const [settings, setSettings] = useState(initialSettings);
  const heading = useRef<HTMLHeadingElement>(null);
  const completed = useRef(false);
  const safeCancel = useRef<HTMLButtonElement>(null);
  const dirty = name.length > 0 || category !== null || market !== "tr" || settings.default_locale !== initialSettings.default_locale || settings.timezone !== initialSettings.timezone || settings.currency !== initialSettings.currency;
  const blocker = useBlocker(() => dirty && !completed.current);
  useEffect(() => { heading.current?.focus(); }, [step]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { if (!completed.current) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const zones = useMemo(() => timezoneOptions(settings.timezone), [settings.timezone]);
  const currencies = CURRENCIES.includes(settings.currency as (typeof CURRENCIES)[number]) ? [...CURRENCIES] : [settings.currency, ...CURRENCIES];
  const last = step === STEPS.length - 1;
  const canContinue = step === 0 ? name.trim().length > 0 : step === 1 ? category !== null : true;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (create.isPending || !canContinue) return;
    if (!last) { setStep(step + 1); return; }
    if (!category || !name.trim()) return;
    create.mutate({ name: name.trim(), business_category: category, market, ...settings }, {
      onSuccess: (workspace) => { completed.current = true; void navigate(`/w/${workspace.id}/more/knowledge`); },
    });
  }
  return <PublicShell title={t("wizard.title")} description={t("entry.wizardIntro")}>
    <Link to="/" className="inline-flex min-h-11 items-center self-start rounded-control text-action underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{t("wizard.back")}</Link>
    <ol aria-label={t("entry.setupProgress")} className="grid grid-cols-3 gap-3">
      {STEPS.map((key, index) => <li key={key} aria-current={index === step ? "step" : undefined} className={`min-w-0 border-t-4 pt-3 text-body transition-all ${index <= step ? "border-action text-primary font-bold" : "border-border text-secondary"}`}><span className="font-semibold">{index + 1}. </span>{t(`entry.steps.${key}`)}</li>)}
    </ol>
    <form onSubmit={submit} noValidate aria-busy={create.isPending} className="flex flex-col gap-5 rounded-2xl border border-border/80 bg-surface p-6 sm:p-8 shadow-card-modern">
      <div><p className="text-metadata text-secondary">{t("wizard.step", { current: step + 1, total: STEPS.length })}</p><h2 ref={heading} tabIndex={-1} className="type-section mt-1 rounded-control focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">{t(`entry.steps.${STEPS[step]}`)}</h2></div>
      {step === 0 ? <TextField label={t("wizard.name")} name="business_name" autoComplete="organization" required maxLength={100} hint={t("entry.nameHint")} value={name} error={nameTouched && !name.trim() ? t("entry.nameRequired") : undefined} onBlur={() => setNameTouched(true)} onChange={(event) => setName(event.target.value)} /> : null}
      {step === 1 ? <fieldset className="grid min-w-0 gap-2"><legend className="mb-3 text-form font-medium">{t("wizard.category")}</legend>{CATEGORIES.map(option => <div key={option} className="rounded-control border border-control px-3 py-1 has-checked:border-action has-checked:bg-assistant"><ChoiceField type="radio" name="business-category" label={t(`wizard.categories.${option}`)} checked={category === option} onChange={() => setCategory(option)} /></div>)}</fieldset> : null}
      {step === 2 ? <>
        <SelectField label={t("wizard.market")} value={market} hint={t("entry.marketHint")} onChange={(event) => { const next = event.target.value === "tr" ? "tr" : "global"; setMarket(next); setSettings(defaultsForMarket(next, browserTimezone())); }}><option value="tr">{t("wizard.markets.tr")}</option><option value="global">{t("wizard.markets.global")}</option></SelectField>
        <SelectField label={t("wizard.locale")} value={settings.default_locale} hint={t("entry.businessLanguageHint")} onChange={(event) => setSettings({ ...settings, default_locale: event.target.value === "en" ? "en" : "tr" })}><option value="tr">{t("settings.languages.tr")}</option><option value="en">{t("settings.languages.en")}</option></SelectField>
        <SelectField label={t("wizard.timezone")} value={settings.timezone} onChange={(event) => setSettings({ ...settings, timezone: event.target.value })}>{zones.map(zone => <option key={zone} value={zone}>{zone}</option>)}</SelectField>
        <SelectField label={t("wizard.currency")} value={settings.currency} onChange={(event) => setSettings({ ...settings, currency: event.target.value })}>{currencies.map(code => <option key={code} value={code}>{code}</option>)}</SelectField>
        <Notice title={t("entry.nextKnowledge")}><p>{t("entry.nextKnowledgeHint")}</p></Notice>
      </> : null}
      {create.error ? <ErrorMessage error={create.error} /> : null}
      <div className="flex flex-wrap gap-3">{step > 0 ? <Button variant="secondary" className="flex-1" disabled={create.isPending} onClick={() => setStep(step - 1)}>{t("wizard.previous")}</Button> : null}<div className="flex min-w-0 flex-1 flex-col gap-2"><Button type="submit" block pending={create.isPending} disabled={!canContinue} disabledReason={!canContinue ? t(step === 0 ? "entry.nameRequired" : "entry.categoryRequired") : undefined}>{last ? create.isPending ? t("wizard.creating") : t("wizard.create") : t("wizard.next")}</Button></div></div>
    </form>
    {blocker.state === "blocked" ? <BottomSheet title={t("entry.leaveTitle")} description={t("entry.leaveHint")} onClose={() => blocker.reset()} initialFocusRef={safeCancel} footer={<div className="flex flex-wrap gap-3"><Button ref={safeCancel} variant="secondary" onClick={() => blocker.reset()}>{t("entry.keepEditing")}</Button><Button variant="danger" disabled={create.isPending} disabledReason={create.isPending ? t("wizard.creating") : undefined} onClick={() => blocker.proceed()}>{t("entry.leave")}</Button></div>}><p className="text-form text-secondary">{t("entry.leaveHint")}</p></BottomSheet> : null}
  </PublicShell>;
}
