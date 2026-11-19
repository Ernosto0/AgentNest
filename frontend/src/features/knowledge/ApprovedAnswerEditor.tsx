import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import type { useCreateAnswer } from "@/features/inbox/hooks";

const INTENTS = [
  "faq",
  "greeting",
  "pricing",
  "hours",
  "location_contact",
  "services",
  "booking",
  "promotions",
  "story_mention",
];

const REPLY_LANGUAGES = ["tr", "en", "ru", "de", "ar"] as const;
type ReplyLanguage = (typeof REPLY_LANGUAGES)[number];

export interface ApprovedAnswerEditorProps {
  create: ReturnType<typeof useCreateAnswer>;
}

export function ApprovedAnswerEditor({ create }: ApprovedAnswerEditorProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [intent, setIntent] = useState("faq");
  const [question, setQuestion] = useState("");
  const [template, setTemplate] = useState("");
  const [language, setLanguage] = useState<ReplyLanguage>("tr");

  const literal = create.error?.fieldErrors.find((e) => e.code === "LITERAL_VALUE");
  const mentionExists = create.error?.fieldErrors.find((e) => e.code === "already_exists");
  const isMention = intent === "story_mention"; // a thank-you answers no question

  return (
    <Card className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
      <div className="border-b border-border pb-3">
        <h2 className="text-lg font-heading font-semibold text-primary">{t("answers.new")}</h2>
      </div>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate(
            { title, intent, question: isMention ? "" : question, template, language },
            {
              onSuccess: () => {
                setTitle("");
                setQuestion("");
                setTemplate("");
              },
            },
          );
        }}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="answer-title" className="text-sm font-medium text-primary">
            {t("answers.fieldTitle")}
          </label>
          <input
            id="answer-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="min-h-11 rounded-control border border-border bg-surface px-3 text-base text-primary font-normal focus:border-control focus-visible:outline-2 focus-visible:outline-focus"
          />
        </div>

        {isMention ? (
          <p className="rounded-panel bg-surface-subtle p-3 text-sm text-secondary border border-border">
            {t("answers.mentionHint")}
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="answer-question" className="text-sm font-medium text-primary">
              {t("answers.fieldQuestion")}
            </label>
            <input
              id="answer-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              className="min-h-11 rounded-control border border-border bg-surface px-3 text-base text-primary font-normal focus:border-control focus-visible:outline-2 focus-visible:outline-focus"
            />
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="answer-template" className="text-sm font-medium text-primary">
            {t("answers.fieldTemplate")}
          </label>
          <textarea
            id="answer-template"
            aria-describedby="answer-template-hint"
            value={template}
            onChange={(event) => setTemplate(event.target.value)}
            rows={4}
            className="rounded-control border border-border bg-surface p-3 text-base text-primary font-normal focus:border-control focus-visible:outline-2 focus-visible:outline-focus"
          />
          <span id="answer-template-hint" className="text-xs text-secondary font-normal">
            {t("answers.templateHint", { example: "{{fact:contact.phone}}" })}
          </span>
        </div>

        <div className="flex flex-wrap gap-4">
          <label className="flex flex-col gap-1.5 min-w-0 text-sm font-medium text-primary flex-1 basis-40">
            {t("answers.fieldIntent")}
            <select
              aria-label={t("answers.fieldIntent")}
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              className="min-h-11 rounded-control border border-border bg-surface px-3 text-base text-primary focus:border-control focus-visible:outline-2 focus-visible:outline-focus"
            >
              {INTENTS.map((name) => (
                <option key={name} value={name}>
                  {t(`answers.intent.${name}`)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5 min-w-0 text-sm font-medium text-primary flex-1 basis-40">
            {t("answers.fieldLanguage")}
            <select
              aria-label={t("answers.fieldLanguage")}
              value={language}
              onChange={(event) => setLanguage(event.target.value as ReplyLanguage)}
              className="min-h-11 rounded-control border border-border bg-surface px-3 text-base text-primary focus:border-control focus-visible:outline-2 focus-visible:outline-focus"
            >
              {REPLY_LANGUAGES.map((lang) => (
                <option key={lang} value={lang}>
                  {t(`answers.lang.${lang}`)}
                </option>
              ))}
            </select>
          </label>
        </div>

        {literal ? (
          <p role="alert" className="rounded-panel bg-danger-subtle p-4 text-sm text-danger border border-border">
            {t("answers.literalValue")}
          </p>
        ) : mentionExists ? (
          <p role="alert" className="rounded-panel bg-danger-subtle p-4 text-sm text-danger border border-border">
            {t("answers.mentionExists")}
          </p>
        ) : create.error ? (
          <ErrorMessage error={create.error} />
        ) : null}

        <div className="pt-1">
          <Button
            type="submit"
            disabled={create.isPending || !title.trim() || (!isMention && !question.trim()) || !template.trim()}
          >
            {t("answers.save")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
