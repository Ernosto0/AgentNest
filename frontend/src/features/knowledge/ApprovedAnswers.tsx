import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useAnswers, useArchiveAnswer, useCreateAnswer } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const INTENTS = ["faq", "greeting", "pricing", "hours", "location_contact", "services", "booking", "promotions"];

/** Replies you approved once and want reused. Values appear only as {{fact:key}} placeholders. */
export function ApprovedAnswers() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canEdit = role === "owner" || role === "manager";
  const answers = useAnswers(workspace.id);
  const create = useCreateAnswer(workspace.id);
  const archive = useArchiveAnswer(workspace.id);
  const [title, setTitle] = useState("");
  const [intent, setIntent] = useState("faq");
  const [question, setQuestion] = useState("");
  const [template, setTemplate] = useState("");
  const [language, setLanguage] = useState<"tr" | "en">("tr");

  const visible = (answers.data ?? []).filter((a) => a.status !== "archived");
  const literal = create.error?.fieldErrors.find((e) => e.code === "LITERAL_VALUE");

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("answers.title")}</h1>
        <p className="mt-1 text-slate-600">{t("answers.intro")}</p>
      </div>

      {answers.isError ? <ErrorMessage error={answers.error} /> : null}
      {answers.data && visible.length === 0 ? <p>{t("answers.empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {visible.map((answer) => (
          <li key={answer.id}>
            <Card className="flex flex-col gap-1" data-testid="answer">
              <p className="font-medium">
                {answer.title}
                {answer.status === "needs_review" ? (
                  <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
                    {t("answers.needsReview")}
                  </span>
                ) : null}
              </p>
              <p className="text-sm text-slate-600">{answer.example_questions.join(" · ")}</p>
              <p className="text-sm break-words whitespace-pre-wrap">{answer.answer_template}</p>
              {canEdit ? (
                <div>
                  <Button variant="ghost" disabled={archive.isPending} onClick={() => archive.mutate(answer)}>
                    {t("answers.archive")}
                  </Button>
                </div>
              ) : null}
            </Card>
          </li>
        ))}
      </ul>

      {canEdit ? (
        <Card>
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              create.mutate(
                { title, intent, question, template, language },
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
            <h2 className="text-lg font-semibold">{t("answers.new")}</h2>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("answers.fieldTitle")}
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="min-h-11 rounded-lg border border-slate-300 px-3 text-base font-normal"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("answers.fieldQuestion")}
              <input
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                className="min-h-11 rounded-lg border border-slate-300 px-3 text-base font-normal"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("answers.fieldTemplate")}
              <textarea
                value={template}
                onChange={(event) => setTemplate(event.target.value)}
                rows={3}
                className="rounded-lg border border-slate-300 p-3 text-base font-normal"
              />
              <span className="text-xs font-normal text-slate-600">{t("answers.templateHint", { example: "{{fact:contact.phone}}" })}</span>
            </label>
            <div className="flex flex-wrap gap-3">
              <select
                aria-label={t("answers.fieldIntent")}
                value={intent}
                onChange={(event) => setIntent(event.target.value)}
                className="min-h-11 rounded-lg border border-slate-300 bg-white px-3"
              >
                {INTENTS.map((name) => (
                  <option key={name} value={name}>
                    {t(`answers.intent.${name}`)}
                  </option>
                ))}
              </select>
              <select
                aria-label={t("answers.fieldLanguage")}
                value={language}
                onChange={(event) => setLanguage(event.target.value as "tr" | "en")}
                className="min-h-11 rounded-lg border border-slate-300 bg-white px-3"
              >
                <option value="tr">{t("answers.lang.tr")}</option>
                <option value="en">{t("answers.lang.en")}</option>
              </select>
            </div>
            {literal ? (
              <p role="alert" className="text-sm text-red-800">
                {t("answers.literalValue")}
              </p>
            ) : create.error ? (
              <ErrorMessage error={create.error} />
            ) : null}
            <div>
              <Button type="submit" disabled={create.isPending || !title.trim() || !question.trim() || !template.trim()}>
                {t("answers.save")}
              </Button>
            </div>
          </form>
        </Card>
      ) : null}
    </div>
  );
}
