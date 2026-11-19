import { PageHeader } from "@/components/Layout";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon } from "@/components/icons";
import { useAnswers, useArchiveAnswer, useCreateAnswer } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ApprovedAnswerEditor } from "./ApprovedAnswerEditor";

function renderTemplatePlaceholders(template: string) {
  const parts = template.split(/(\{\{[^}]+\}\})/g);
  return parts.map((part, index) => {
    if (part.startsWith("{{") && part.endsWith("}}")) {
      return (
        <code
          key={index}
          className="rounded-control bg-surface-subtle px-2 py-0.5 font-mono text-xs font-semibold text-action border border-border"
        >
          {part}
        </code>
      );
    }
    return part;
  });
}

/** Replies you approved once and want reused. Values appear only as {{fact:key}} placeholders. */
export function ApprovedAnswers() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canEdit = role === "owner" || role === "manager";
  const answers = useAnswers(workspace.id);
  const create = useCreateAnswer(workspace.id);
  const archive = useArchiveAnswer(workspace.id);

  const visible = (answers.data ?? []).filter((a) => a.status !== "archived");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to={`/w/${workspace.id}/more/knowledge`}
          className="inline-flex min-h-11 items-center font-medium text-action hover:text-action-hover underline focus-visible:outline-2 focus-visible:outline-focus"
        >
          ← {t("answers.back")}
        </Link>
        <PageHeader title={t("answers.title")} description={t("answers.intro")} />
      </div>

      {!canEdit ? (
        <p className="rounded-panel bg-surface-subtle p-4 text-sm text-secondary border border-border">
          {t("answers.staffNote")}
        </p>
      ) : null}

      {answers.isError ? <ErrorMessage error={answers.error} /> : null}
      {answers.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {answers.data && visible.length === 0 ? (
        <EmptyState title={t("answers.empty")} />
      ) : null}

      <div className={`grid min-w-0 items-start gap-6 ${canEdit && visible.length > 0 ? "xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]" : ""}`}>
      <ul className="flex min-w-0 flex-col gap-3">
        {visible.map((answer) => (
          <li key={answer.id}>
            <Card className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5 shadow-xs" data-testid="answer">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-primary">{answer.title}</span>
                  <span className="rounded-control bg-surface-subtle px-2.5 py-0.5 text-xs font-medium text-secondary border border-border">
                    {t(`answers.intent.${answer.intent}`)}
                  </span>
                  <span className="rounded-control bg-surface-subtle px-2 py-0.5 text-xs font-mono font-medium text-secondary border border-border uppercase">
                    {answer.language}
                  </span>
                </div>
                {answer.status === "needs_review" ? (
                  <span className="inline-flex items-center gap-1.5 rounded-control bg-attention-subtle px-2.5 py-0.5 text-xs font-semibold text-attention border border-border">
                    <AlertIcon className="text-xs" aria-hidden="true" />
                    <span>{t("answers.needsReview")}</span>
                  </span>
                ) : null}
              </div>

              {answer.example_questions.length > 0 ? (
                <p className="text-sm text-secondary italic">
                  "{answer.example_questions.join(" · ")}"
                </p>
              ) : null}

              <div className="rounded-panel bg-surface-subtle p-4 text-sm text-primary break-words whitespace-pre-wrap border border-border">
                {renderTemplatePlaceholders(answer.answer_template)}
              </div>

              {canEdit ? (
                <div className="pt-1">
                  <Button variant="ghost" disabled={archive.isPending} onClick={() => archive.mutate(answer)}>
                    {t("answers.archive")}
                  </Button>
                </div>
              ) : null}
            </Card>
          </li>
        ))}
      </ul>

      {canEdit ? <ApprovedAnswerEditor create={create} /> : null}
      </div>
    </div>
  );
}
