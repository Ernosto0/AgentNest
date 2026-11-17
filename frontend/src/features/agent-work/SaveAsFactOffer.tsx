import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CheckIcon } from "@/components/icons";
import { useResolveCandidate } from "@/features/knowledge/hooks";
import type { Schema } from "@/features/agent/hooks";

/**
 * After an owner answer: "Save this as a verified fact?" with one tap. The tap accepts the
 * unverified candidate the answer already created, through the ordinary accept endpoint. The text
 * of the answer never verifies anything by itself. An answer with a price, hours or a contact is
 * sent to the typed editor in Suggestions instead.
 */
export function SaveAsFactOffer({
  workspaceId,
  answer,
}: {
  workspaceId: string;
  answer: Schema<"AnswerOut">;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const resolve = useResolveCandidate(workspaceId);
  if (!answer.candidate_id || !answer.candidate_status) return null;
  const candidateId = answer.candidate_id;

  if (answer.candidate_status === "accepted") {
    return (
      <p role="status" className="flex items-center gap-2 text-sm font-medium text-success">
        <CheckIcon aria-hidden="true" />
        {t("agentWork.learning.saved")}
      </p>
    );
  }
  if (answer.candidate_status !== "pending") return null;

  return (
    <section
      aria-labelledby="save-fact-title"
      data-testid="save-as-fact"
      className="flex min-w-0 flex-col gap-3 rounded-panel border border-action/30 bg-assistant/40 p-4"
    >
      <div className="flex flex-col gap-1">
        <h2 id="save-fact-title" className="font-heading text-base font-semibold text-primary">
          {t("agentWork.learning.offerTitle")}
        </h2>
        <p className="text-sm text-secondary">
          {answer.candidate_editor_type ? t("agentWork.learning.needsEditor") : t("agentWork.learning.offerHint")}
        </p>
      </div>
      {resolve.error ? <ErrorMessage error={resolve.error} /> : null}
      <div className="flex flex-wrap gap-2">
        {answer.candidate_editor_type ? (
          <Link
            className="inline-flex min-h-11 items-center rounded-control bg-action px-4 text-body font-semibold text-on-action hover:bg-action-hover"
            to={`/w/${workspaceId}/more/knowledge/suggestions`}
          >
            {t("agentWork.learning.review")}
          </Link>
        ) : (
          <Button
            disabled={resolve.isPending}
            onClick={() =>
              resolve.mutate(
                { candidateId, action: "accept" },
                { onSuccess: () => client.invalidateQueries({ queryKey: ["agent", workspaceId] }) },
              )
            }
          >
            {t("agentWork.learning.save")}
          </Button>
        )}
      </div>
    </section>
  );
}
