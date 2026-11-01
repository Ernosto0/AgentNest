import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useSavePersonality, useAgentPersonality, type Schema } from "./hooks";

export const FIELD =
  "min-h-11 w-full min-w-0 rounded-control border border-border bg-surface px-3 py-2 text-base text-primary shadow-xs focus-visible:outline-2 focus-visible:outline-focus disabled:opacity-60";

const choices = {
  tone: ["warm", "neutral", "direct"],
  formality: ["casual", "professional"],
  length: ["short", "medium"],
  emoji: ["none", "sparse"],
  dm_style: ["conversational", "concise"],
  comment_style: ["conversational", "concise"],
} as const;

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

  return (
    <Card className="flex flex-col gap-4">
      <div className="border-b border-border pb-3">
        <h2 className="text-lg font-heading font-semibold text-primary">{t("agent.personality")}</h2>
      </div>

      <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
        <span>{t("agent.goals")}</span>
        <textarea
          className={FIELD}
          rows={3}
          maxLength={500}
          value={goals}
          disabled={!editable || save.isPending}
          onChange={(e) => {
            save.reset();
            setGoals(e.target.value);
          }}
        />
      </label>
      <p className="text-sm text-secondary">{t("agent.goalsHint")}</p>

      <div className="grid gap-4 sm:grid-cols-2">
        {Object.entries(choices).map(([key, values]) => (
          <label key={key} className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
            <span>{t(`agent.voice.${key}`)}</span>
            <select
              className={FIELD}
              disabled={!editable || save.isPending}
              value={draft[key as keyof typeof choices]}
              onChange={(e) => {
                save.reset();
                setPreview(false);
                setDraft({ ...draft, [key]: e.target.value });
              }}
            >
              {values.map((v) => (
                <option key={v} value={v}>
                  {t(`agent.voice.${v}`)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <div className="flex flex-col gap-3">
        {(["tr", "en"] as const).map((lang) => (
          <label key={lang} className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
            <span>{t(`agent.examples_${lang}`)}</span>
            <textarea
              className={FIELD}
              rows={2}
              disabled={!editable || save.isPending}
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

      <div className="flex flex-wrap items-center gap-3 pt-2">
        {editable ? (
          <Button
            disabled={save.isPending}
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
          <p className="text-sm font-medium text-secondary">{t("agent.managerOnly")}</p>
        )}

        <Button variant="secondary" onClick={() => setPreview((v) => !v)}>
          {t("agent.previewVoice")}
        </Button>
      </div>

      {save.error ? (
        <div className="flex flex-col gap-2 rounded-control border border-danger bg-danger-subtle p-3">
          <ErrorMessage error={save.error} />
          <p className="text-sm text-danger font-medium">{t("agent.reloadWarning")}</p>
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

      {save.isSuccess ? (
        <p role="status" className="text-sm font-medium text-success">
          {t("agent.saved")}
        </p>
      ) : null}

      {preview ? (
        <aside
          className="flex flex-col gap-2 rounded-control border border-border bg-surface-subtle p-4 shadow-xs"
          aria-label={t("agent.previewVoice")}
        >
          <p className="text-xs text-muted">{t("agent.previewDisclosure")}</p>
          <div className="flex flex-col gap-1.5 pt-2 text-sm">
            <p className="font-medium text-secondary">{t("agent.sampleCustomer")}</p>
            <p className="font-semibold text-primary">
              {draft.examples?.[i18n.language === "en" ? "en" : "tr"]?.[0] ||
                t(`agent.sample_${draft.tone}`)}
              {draft.emoji === "sparse" ? " " + String.fromCodePoint(0x1f642) : ""}
            </p>
          </div>
        </aside>
      ) : null}
    </Card>
  );
}
