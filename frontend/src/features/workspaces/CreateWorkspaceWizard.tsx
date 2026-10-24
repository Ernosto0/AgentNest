import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { Workspace, WorkspaceCreateBody } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { TextField } from "@/components/TextField";
import { meKey } from "@/features/auth/hooks";
import { SelectField } from "@/features/knowledge/editors/fields";
import {
  CURRENCIES,
  browserTimezone,
  defaultsForMarket,
  timezoneOptions,
  type Market,
} from "./wizardDefaults";

const CATEGORIES = [
  "beauty_wellness",
  "food_beverage",
  "retail",
  "fitness",
  "health_clinic",
  "education",
  "hospitality",
  "services",
  "other",
] as const;
const STEPS = ["name", "category", "locale"] as const;

function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation<Workspace, AppError, WorkspaceCreateBody>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/workspaces", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meKey }),
  });
}

/** Name → category → market, language, time zone and currency; then the knowledge checklist. */
export function CreateWorkspaceWizard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateWorkspace();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [category, setCategory] = useState<(typeof CATEGORIES)[number] | null>(null);
  const [market, setMarket] = useState<Market>("tr");
  const [settings, setSettings] = useState(() => defaultsForMarket("tr", browserTimezone()));

  const zones = useMemo(() => timezoneOptions(settings.timezone), [settings.timezone]);
  const currencies = CURRENCIES.includes(settings.currency as (typeof CURRENCIES)[number])
    ? [...CURRENCIES]
    : [settings.currency, ...CURRENCIES];

  const chooseMarket = (next: Market) => {
    setMarket(next);
    setSettings(defaultsForMarket(next, browserTimezone()));
  };

  const last = step === STEPS.length - 1;
  const canContinue =
    (step === 0 && name.trim().length > 0) ||
    (step === 1 && category !== null) ||
    step === 2;

  const submit = () => {
    if (!category) return;
    create.mutate(
      { name: name.trim(), business_category: category, market, ...settings },
      { onSuccess: (workspace) => void navigate(`/w/${workspace.id}/more/knowledge`) },
    );
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col gap-5 px-4 py-8">
      <div>
        <Link
          to="/"
          className="inline-flex min-h-11 items-center text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600"
        >
          {t("wizard.back")}
        </Link>
        <h1 className="text-2xl font-semibold">{t("wizard.title")}</h1>
        <p className="mt-1 text-slate-600" aria-live="polite">
          {t("wizard.step", { current: step + 1, total: STEPS.length })}
        </p>
      </div>

      <Card className="flex flex-col gap-4">
        {step === 0 ? (
          <TextField
            label={t("wizard.name")}
            value={name}
            maxLength={100}
            autoFocus
            onChange={(event) => setName(event.target.value)}
          />
        ) : null}

        {step === 1 ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-base font-medium">{t("wizard.category")}</legend>
            {CATEGORIES.map((option) => (
              <label
                key={option}
                className="flex min-h-14 items-center gap-3 rounded-xl p-3 ring-1 ring-slate-300 has-checked:bg-indigo-50 has-checked:ring-indigo-600"
              >
                <input
                  type="radio"
                  name="business-category"
                  className="size-5"
                  checked={category === option}
                  onChange={() => setCategory(option)}
                />
                <span>{t(`wizard.categories.${option}`)}</span>
              </label>
            ))}
          </fieldset>
        ) : null}

        {step === 2 ? (
          <div className="flex flex-col gap-4">
            <SelectField
              label={t("wizard.market")}
              value={market}
              onChange={(event) => chooseMarket(event.target.value === "tr" ? "tr" : "global")}
            >
              <option value="tr">{t("wizard.markets.tr")}</option>
              <option value="global">{t("wizard.markets.global")}</option>
            </SelectField>
            <SelectField
              label={t("wizard.locale")}
              value={settings.default_locale}
              onChange={(event) =>
                setSettings({ ...settings, default_locale: event.target.value === "en" ? "en" : "tr" })
              }
            >
              <option value="tr">{t("settings.languages.tr")}</option>
              <option value="en">{t("settings.languages.en")}</option>
            </SelectField>
            <SelectField
              label={t("wizard.timezone")}
              value={settings.timezone}
              onChange={(event) => setSettings({ ...settings, timezone: event.target.value })}
            >
              {zones.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </SelectField>
            <SelectField
              label={t("wizard.currency")}
              value={settings.currency}
              onChange={(event) => setSettings({ ...settings, currency: event.target.value })}
            >
              {currencies.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </SelectField>
          </div>
        ) : null}

        {create.error ? <ErrorMessage error={create.error} /> : null}

        <div className="flex gap-3">
          {step > 0 ? (
            <Button variant="secondary" className="flex-1" onClick={() => setStep(step - 1)}>
              {t("wizard.previous")}
            </Button>
          ) : null}
          {last ? (
            <Button className="flex-1" disabled={create.isPending || !name.trim()} onClick={submit}>
              {create.isPending ? t("wizard.creating") : t("wizard.create")}
            </Button>
          ) : (
            <Button className="flex-1" disabled={!canContinue} onClick={() => setStep(step + 1)}>
              {t("wizard.next")}
            </Button>
          )}
        </div>
      </Card>
    </main>
  );
}
