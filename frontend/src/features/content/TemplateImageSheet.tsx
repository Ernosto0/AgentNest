import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import type { ContentType, Fact, MediaAsset, TemplateBody } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CheckIcon, SpinnerIcon } from "@/components/icons";
import { TextField } from "@/components/TextField";
import { newRequestId } from "@/features/commands/hooks";
import { useFacts } from "@/features/knowledge/hooks";
import { pickLabel } from "@/features/knowledge/labels";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCreateContent } from "./hooks";
import { useCreateTemplateImage, useTemplatePreview } from "./templateHooks";

export type TemplateId = "price_card" | "hours_card" | "services_list" | "announcement";
export type CardFormat = "story" | "feed";

const TEMPLATES: readonly TemplateId[] = ["price_card", "hours_card", "services_list", "announcement"];
const FORMATS: readonly CardFormat[] = ["story", "feed"];
const HOURS_KEY = "hours.weekly" as const;
const SERVICES_MIN = 2;
const SERVICES_MAX = 6;
const HEADLINE_MAX = 180;
const BODY_MAX = 1600;
const DATE_LINE_MAX = 120;
const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";
const SELECT =
  "min-h-11 w-full rounded-control border border-control bg-surface px-3 text-form text-primary shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

const contentTypeOf = (format: CardFormat): ContentType => (format === "story" ? "story_image" : "feed_image");

interface SheetProps {
  /** The format the sheet opens with (a story prompt opens it at `story`). */
  initialFormat: CardFormat;
  onClose: () => void;
  /**
   * Attach the stored image to the draft that is open. Without it the sheet starts a new draft with
   * the image and opens it. Either way nothing is scheduled, approved or published here.
   */
  onAttach?: (asset: MediaAsset) => void;
}

/**
 * "Make an image from a template": pick a template, fill it from verified facts (the values are
 * never typed, only chosen by key), watch the preview and keep the picture as a normal draft image.
 */
export function TemplateImageSheet({ initialFormat, onClose, onAttach }: SheetProps) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const navigate = useNavigate();
  const ids = { price: useId(), headline: useId(), body: useId(), dateLine: useId() };
  const facts = useFacts(workspace.id);
  const store = useCreateTemplateImage(workspace.id);
  const createDraft = useCreateContent(workspace.id);

  const [template, setTemplate] = useState<TemplateId>("price_card");
  const [format, setFormat] = useState<CardFormat>(initialFormat);
  const [priceKey, setPriceKey] = useState("");
  const [serviceKeys, setServiceKeys] = useState<string[]>([]);
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [dateLine, setDateLine] = useState("");
  const [panel, setPanel] = useState<"fields" | "preview">("fields");
  const [done, setDone] = useState<string | null>(null);

  const usable: Fact[] = (facts.data ?? []).filter((fact) => fact.usable);
  const prices = usable.filter((fact) => fact.value_type === "money");
  const hoursReady = usable.some((fact) => fact.key === HOURS_KEY && fact.value_type === "weekly_hours");
  const label = (fact: Fact) => pickLabel(fact.label, i18n.language);

  let input: TemplateBody | null = null;
  if (template === "price_card" && priceKey) input = { template, format, fact_key: priceKey };
  else if (template === "hours_card" && hoursReady) input = { template, format, fact_key: HOURS_KEY };
  else if (template === "services_list" && serviceKeys.length >= SERVICES_MIN && serviceKeys.length <= SERVICES_MAX)
    input = { template, format, fact_keys: serviceKeys };
  else if (template === "announcement" && headline.trim() && body.trim())
    input = {
      template,
      format,
      headline: headline.trim(),
      body: body.trim(),
      ...(dateLine.trim() ? { date_line: dateLine.trim() } : {}),
    };

  const preview = useTemplatePreview(workspace.id, input);
  const busy = store.isPending || createDraft.isPending;
  const error = store.error ?? createDraft.error;

  const toggleService = (key: string) =>
    setServiceKeys((current) =>
      current.includes(key) ? current.filter((k) => k !== key) : current.length < SERVICES_MAX ? [...current, key] : current,
    );

  const draftTitle = () => {
    const name = t(`content.template.names.${template}`);
    const detail =
      template === "price_card"
        ? label(prices.find((fact) => fact.key === priceKey) ?? ({ label: {} } as Fact))
        : template === "announcement"
          ? headline.trim()
          : "";
    return (detail ? `${name}: ${detail}` : name).slice(0, 200);
  };

  const use = () => {
    if (!input) return;
    store.mutate(input, {
      onSuccess: (asset) => {
        if (onAttach) {
          onAttach(asset);
          onClose();
          return;
        }
        createDraft.mutate(
          {
            content_type: contentTypeOf(format),
            title: draftTitle(),
            media_asset_id: asset.id,
            client_request_id: newRequestId(),
          },
          { onSuccess: (item) => setDone(item.id) },
        );
      },
    });
  };

  const fieldsPanel = (
    <div className={`min-w-0 flex-col gap-5 ${panel === "fields" ? "flex" : "hidden md:flex"}`}>
      <p className="text-sm text-secondary">{t("content.template.intro")}</p>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-semibold text-primary">{t("content.template.templatesLabel")}</legend>
        <div role="radiogroup" aria-label={t("content.template.templatesLabel")} className="grid grid-cols-2 gap-2">
          {TEMPLATES.map((id) => (
            <label
              key={id}
              className={`flex min-h-11 cursor-pointer items-center justify-center rounded-control border px-3 py-2 text-center text-sm font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-focus ${
                template === id ? "border-action bg-action-subtle text-primary" : "border-border bg-surface text-secondary hover:text-primary"
              }`}
            >
              <input
                type="radio"
                name={`${ids.price}-template`}
                value={id}
                checked={template === id}
                onChange={() => setTemplate(id)}
                className="sr-only"
              />
              {t(`content.template.names.${id}`)}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-semibold text-primary">{t("content.template.formatLabel")}</legend>
        <div role="radiogroup" aria-label={t("content.template.formatLabel")} className="inline-flex gap-2">
          {FORMATS.map((id) => (
            <label
              key={id}
              className={`inline-flex min-h-11 cursor-pointer items-center rounded-control border px-4 text-sm font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-focus ${
                format === id ? "border-action bg-action-subtle text-primary" : "border-border bg-surface text-secondary hover:text-primary"
              }`}
            >
              <input
                type="radio"
                name={`${ids.price}-format`}
                value={id}
                checked={format === id}
                onChange={() => setFormat(id)}
                className="sr-only"
              />
              {t(`content.template.format.${id}`)}
            </label>
          ))}
        </div>
      </fieldset>

      {template === "price_card" ? (
        prices.length === 0 && facts.isSuccess ? (
          <NoFacts message={t("content.template.noPrices")} />
        ) : (
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.price} className="text-sm font-semibold text-primary">
              {t("content.template.priceLabel")}
            </label>
            <select id={ids.price} value={priceKey} onChange={(event) => setPriceKey(event.target.value)} className={SELECT}>
              <option value="">{t("content.template.priceChoose")}</option>
              {prices.map((fact) => (
                <option key={fact.key} value={fact.key}>
                  {`${label(fact)} · ${fact.display}`}
                </option>
              ))}
            </select>
          </div>
        )
      ) : null}

      {template === "hours_card" ? (
        hoursReady || !facts.isSuccess ? (
          <p className="flex items-center gap-2 text-sm text-secondary">
            <CheckIcon className="text-base text-success" />
            <span>{t("content.template.hoursReady")}</span>
          </p>
        ) : (
          <NoFacts message={t("content.template.hoursMissing")} />
        )
      ) : null}

      {template === "services_list" ? (
        prices.length === 0 && facts.isSuccess ? (
          <NoFacts message={t("content.template.noPrices")} />
        ) : (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="text-sm font-semibold text-primary">{t("content.template.servicesLabel")}</legend>
            <p className="text-xs text-secondary">
              {t("content.template.servicesHint")} {t("content.template.servicesCount", { count: serviceKeys.length })}
            </p>
            <ul className="flex flex-col gap-1.5">
              {prices.map((fact) => (
                <li key={fact.key}>
                  <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-control border border-border bg-surface px-3 py-2 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-focus">
                    <input
                      type="checkbox"
                      checked={serviceKeys.includes(fact.key)}
                      onChange={() => toggleService(fact.key)}
                      className="size-5 shrink-0"
                    />
                    <span className="min-w-0 break-words">{`${label(fact)} · ${fact.display}`}</span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        )
      ) : null}

      {template === "announcement" ? (
        <div className="flex flex-col gap-4">
          <TextField
            label={t("content.template.headline")}
            value={headline}
            maxLength={HEADLINE_MAX}
            onChange={(event) => setHeadline(event.target.value)}
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.body} className="text-sm font-semibold text-primary">
              {t("content.template.body")}
            </label>
            <textarea
              id={ids.body}
              value={body}
              rows={4}
              maxLength={BODY_MAX}
              onChange={(event) => setBody(event.target.value)}
              className={`min-h-24 w-full rounded-control border border-control bg-surface p-3 text-form text-primary shadow-xs ${FOCUS}`}
            />
            <p className="text-end text-xs tabular-nums text-secondary">
              {t("content.template.counter", { count: body.length, max: BODY_MAX })}
            </p>
          </div>
          <TextField
            label={t("content.template.dateLine")}
            value={dateLine}
            maxLength={DATE_LINE_MAX}
            onChange={(event) => setDateLine(event.target.value)}
          />
          <p className="text-xs text-secondary">{t("content.template.announcementHint")}</p>
        </div>
      ) : null}
    </div>
  );

  const previewPanel = (
    <div
      className={`min-w-0 flex-col gap-2 ${panel === "preview" ? "flex" : "hidden md:flex"}`}
      data-testid="template-preview"
    >
      <h3 className="text-sm font-semibold text-primary">{t("content.template.previewLabel")}</h3>
      <div
        aria-live="polite"
        className="flex min-h-48 items-center justify-center overflow-hidden rounded-panel border border-border bg-surface-subtle p-2"
      >
        {preview.status === "error" ? (
          <div className="flex w-full flex-col gap-2">
            <p className="flex items-center gap-2 text-sm text-danger">
              <AlertIcon className="shrink-0 text-base" />
              <span>{t("content.template.previewFailed")}</span>
            </p>
            <ErrorMessage error={preview.error} />
          </div>
        ) : preview.url ? (
          <div className="relative">
            <img
              src={preview.url}
              alt={t("content.template.previewAlt")}
              className={`max-h-[60vh] w-auto max-w-full rounded-control border border-border/60 object-contain ${preview.status === "loading" ? "opacity-60" : ""}`}
            />
            {preview.status === "loading" ? (
              <SpinnerIcon className="absolute top-2 right-2 text-lg text-action motion-safe:animate-spin" />
            ) : null}
          </div>
        ) : preview.status === "loading" ? (
          <p className="flex items-center gap-2 text-sm text-secondary">
            <SpinnerIcon className="text-base text-action motion-safe:animate-spin" />
            <span>{t("content.template.previewLoading")}</span>
          </p>
        ) : (
          <p className="p-4 text-center text-sm text-secondary">{t("content.template.previewEmpty")}</p>
        )}
      </div>
    </div>
  );

  return (
    <BottomSheet
      title={t("content.template.title")}
      onClose={onClose}
      dismissible={!busy}
      footer={
        done ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => navigate(`/w/${workspace.id}/content/${done}`)}>{t("content.template.openDraft")}</Button>
            <Button variant="secondary" onClick={onClose}>
              {t("content.template.close")}
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={!input || busy || preview.status === "error"} pending={busy} onClick={use}>
              {busy ? t("content.template.using") : t("content.template.use")}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={onClose}>
              {t("content.template.close")}
            </Button>
          </div>
        )
      }
    >
      {done ? (
        <p role="status" className="flex items-center gap-2 rounded-panel border border-success/30 bg-success-subtle p-4 text-sm font-semibold text-success">
          <CheckIcon className="shrink-0 text-base" />
          <span>{t("content.template.savedDraft")}</span>
        </p>
      ) : (
        <div className="flex min-w-0 flex-col gap-4">
          <div role="group" aria-label={t("content.template.title")} className="flex gap-2 md:hidden">
            {(["fields", "preview"] as const).map((name) => (
              <Button key={name} variant={panel === name ? "primary" : "secondary"} aria-pressed={panel === name} onClick={() => setPanel(name)}>
                {t(name === "fields" ? "content.template.fields" : "content.template.previewLabel")}
              </Button>
            ))}
          </div>
          <div className="grid min-w-0 items-start gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            {fieldsPanel}
            {previewPanel}
          </div>
          {error ? <ErrorMessage error={error} /> : null}
        </div>
      )}
    </BottomSheet>
  );
}

function NoFacts({ message }: { message: string }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  return (
    <div role="status" className="flex flex-col gap-2 rounded-panel border border-attention bg-attention-subtle p-3.5 text-sm text-attention">
      <p>{message}</p>
      <Link
        to={`/w/${workspace.id}/more/knowledge`}
        className="inline-flex min-h-11 items-center font-semibold underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        {t("content.template.openKnowledge")}
      </Link>
    </div>
  );
}
