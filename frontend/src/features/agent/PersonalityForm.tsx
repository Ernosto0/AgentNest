import { useDirtyForm } from "@/components/DirtyForms";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, ChatIcon, CheckIcon, CommentIcon, SparkIcon } from "@/components/icons";
import { Segmented, SectionTitle, Surface } from "./AgentParts";
import { useSavePersonality, useAgentPersonality, type Schema } from "./hooks";

export const FIELD =
  "min-h-11 w-full min-w-0 rounded-control border border-control/50 bg-surface px-3 py-2 text-base text-primary transition-colors hover:border-control focus-visible:outline-2 focus-visible:outline-focus focus:border-action disabled:opacity-60";

type Voice = Schema<"Personality">;

const STYLE = {
  tone: ["warm", "neutral", "direct"],
  formality: ["casual", "professional"],
  length: ["short", "medium"],
  emoji: ["none", "sparse"],
} as const;
const CHANNELS = {
  dm_style: ["conversational", "concise"],
  comment_style: ["conversational", "concise"],
} as const;
const GOALS_MAX = 500;

/**
 * Goals and voice (ui-spec §4.6). Saves are bound to the loaded version; a stale save keeps the
 * edits on screen and offers an explicit reload. The preview is a static local sample, never a model run.
 */
export function PersonalityForm({
  ws,
  account,
  data,
  editable,
}: {
  ws: string;
  account: string;
  data: Schema<"PersonalityOut">;
  editable: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [draft, setDraft] = useState(data.personality);
  const [version, setVersion] = useState(data.version);
  const [goals, setGoals] = useState(data.goals);
  const [preview, setPreview] = useState(false);
  const save = useSavePersonality(ws, account);
  const current = useAgentPersonality(ws, account);
  const dirty =
    goals !== (current.data?.goals ?? data.goals) ||
    JSON.stringify(draft) !== JSON.stringify(current.data?.personality ?? data.personality);
  useDirtyForm(dirty);
  const locked = !editable || save.isPending;

  const choose = (key: keyof Voice, value: string) => {
    save.reset();
    setPreview(false);
    setDraft({ ...draft, [key]: value });
  };
  const options = (values: readonly string[]) => values.map((v) => ({ value: v, label: t(`agent.voice.${v}`) }));
  const sample =
    draft.examples?.[i18n.language === "en" ? "en" : "tr"]?.[0] || t(`agent.sample_${draft.tone}`);

  return (
    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Surface aria-labelledby="agent-voice-title" className="gap-6 p-4 sm:p-6">
        <SectionTitle id="agent-voice-title" icon={<SparkIcon />} title={t("agent.personality")} meta={t("agent.voiceIntro")} />

        <div className="flex flex-col gap-1.5">
          <label htmlFor="agent-goals" className="text-metadata font-semibold text-primary">
            {t("agent.goals")}
          </label>
          <textarea
            id="agent-goals"
            aria-describedby="agent-goals-hint"
            className={`${FIELD} field-sizing-content min-h-24`}
            rows={3}
            maxLength={GOALS_MAX}
            value={goals}
            disabled={locked}
            onChange={(e) => {
              save.reset();
              setGoals(e.target.value);
            }}
          />
          <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-secondary">
            <p id="agent-goals-hint">{t("agent.goalsHint")}</p>
            <span className="tabular-nums">{t("agent.composer.count", { count: goals.length, max: GOALS_MAX })}</span>
          </div>
        </div>

        <section aria-labelledby="agent-voice-style" className="flex flex-col gap-4 border-t border-border pt-5">
          <h3 id="agent-voice-style" className="font-heading text-body font-semibold text-primary">{t("agent.voiceSections.style")}</h3>
          <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            {(Object.keys(STYLE) as (keyof typeof STYLE)[]).map((key) => (
              <Segmented key={key} label={t(`agent.voice.${key}`)} value={draft[key]} options={options(STYLE[key])} onChange={(v) => choose(key, v)} disabled={locked} />
            ))}
          </div>
        </section>

        <section aria-labelledby="agent-voice-channels" className="flex flex-col gap-4 border-t border-border pt-5">
          <h3 id="agent-voice-channels" className="font-heading text-body font-semibold text-primary">{t("agent.voiceSections.channels")}</h3>
          <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            {(Object.keys(CHANNELS) as (keyof typeof CHANNELS)[]).map((key) => (
              <Segmented key={key} label={t(`agent.voice.${key}`)} value={draft[key]} options={options(CHANNELS[key])} onChange={(v) => choose(key, v)} disabled={locked} />
            ))}
          </div>
        </section>

        <section aria-labelledby="agent-voice-examples" className="flex flex-col gap-3 border-t border-border pt-5">
          <div>
            <h3 id="agent-voice-examples" className="font-heading text-body font-semibold text-primary">{t("agent.voiceSections.examples")}</h3>
            <p className="text-xs text-secondary">{t("agent.voiceSections.examplesHint")}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {(["tr", "en"] as const).map((lang) => (
              <label key={lang} className="flex flex-col gap-1.5">
                <span className="text-metadata font-semibold text-primary">{t(`agent.examples_${lang}`)}</span>
                <textarea
                  className={`${FIELD} field-sizing-content min-h-20`}
                  rows={2}
                  disabled={locked}
                  value={draft.examples?.[lang]?.join("\n") ?? ""}
                  maxLength={321}
                  onChange={(e) => {
                    save.reset();
                    setDraft({
                      ...draft,
                      examples: {
                        ...draft.examples,
                        [lang]: e.target.value
                          .split("\n")
                          .slice(0, 2)
                          .map((s) => s.slice(0, 160)),
                      },
                    });
                  }}
                />
              </label>
            ))}
          </div>
        </section>

        <div className="flex flex-col gap-3 border-t border-border pt-5">
          <div className="flex flex-wrap items-center gap-3">
            {editable ? (
              <Button
                pending={save.isPending}
                onClick={() =>
                  save.mutate(
                    { expected_version: version, personality: draft, goals },
                    { onSuccess: (saved) => setVersion(saved.version) },
                  )
                }
              >
                {t("agent.savePersonality")}
              </Button>
            ) : (
              <p className="text-metadata font-medium text-secondary">{t("agent.managerOnly")}</p>
            )}
            {editable && dirty && !save.isPending && !save.error ? (
              <span className="text-xs font-medium text-attention">{t("agent.unsaved")}</span>
            ) : null}
            {save.isSuccess ? (
              <p role="status" className="inline-flex items-center gap-1.5 text-metadata font-semibold text-success">
                <CheckIcon aria-hidden="true" />
                {t("agent.saved")}
              </p>
            ) : null}
          </div>

          {save.error ? (
            <div className="flex flex-col gap-2.5 rounded-xl bg-danger-subtle p-4">
              <ErrorMessage error={save.error} />
              <p className="flex items-start gap-2 text-metadata font-medium text-danger">
                <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
                {t("agent.reloadWarning")}
              </p>
              <div>
                <Button
                  variant="secondary"
                  disabled={current.isFetching}
                  onClick={() => {
                    void current.refetch().then((result) => {
                      if (result.data) {
                        setDraft(result.data.personality);
                        setGoals(result.data.goals);
                        setVersion(result.data.version);
                        save.reset();
                      }
                    });
                  }}
                >
                  {t("agent.reloadCurrent")}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </Surface>

      <aside aria-labelledby="agent-voice-summary" className="flex min-w-0 flex-col gap-4 rounded-2xl bg-assistant p-4 sm:p-5 lg:sticky lg:top-24">
        <div>
          <h2 id="agent-voice-summary" className="font-heading text-base font-semibold text-primary">{t("agent.voiceSummary.title")}</h2>
          <p className="text-xs text-secondary">{t("agent.voiceSummary.hint")}</p>
        </div>
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-border/70 ring-1 ring-border/70">
          {(["tone", "formality", "length", "emoji"] as const).map((key) => (
            <div key={key} className="flex min-w-0 flex-col bg-surface/90 px-3 py-2">
              <dt className="text-[11px] font-medium text-secondary">{t(`agent.voice.${key}`)}</dt>
              <dd className="text-metadata font-semibold text-primary">{t(`agent.voice.${draft[key]}`)}</dd>
            </div>
          ))}
        </dl>
        <ul className="flex flex-col gap-1.5 text-metadata text-primary">
          <li className="flex items-center gap-2">
            <ChatIcon aria-hidden="true" className="shrink-0 text-action" />
            {t("agent.voiceSummary.dm", { style: t(`agent.voice.${draft.dm_style}`) })}
          </li>
          <li className="flex items-center gap-2">
            <CommentIcon aria-hidden="true" className="shrink-0 text-action" />
            {t("agent.voiceSummary.comment", { style: t(`agent.voice.${draft.comment_style}`) })}
          </li>
        </ul>

        <Button variant="secondary" onClick={() => setPreview((v) => !v)} aria-expanded={preview} aria-controls="agent-voice-preview">
          {t("agent.previewVoice")}
        </Button>
        {preview ? (
          <div id="agent-voice-preview" role="region" aria-label={t("agent.previewVoice")} className="flex flex-col gap-2.5 rounded-xl bg-surface p-3.5">
            <p className="self-start rounded-2xl rounded-bl-md bg-surface-subtle px-3.5 py-2 text-metadata text-primary">{t("agent.sampleCustomer")}</p>
            <p className="max-w-[90%] self-end rounded-2xl rounded-br-md bg-action px-3.5 py-2 text-metadata font-medium text-on-action [overflow-wrap:anywhere]">
              {sample}
              {draft.emoji === "sparse" ? " " + String.fromCodePoint(0x1f642) : ""}
            </p>
            <p className="border-t border-border pt-2 text-xs text-secondary">{t("agent.previewDisclosure")}</p>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
