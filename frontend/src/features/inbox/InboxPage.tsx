import { useTranslation } from "react-i18next";
import { useLocation, useSearchParams } from "react-router-dom";
import { ChatIcon, CommentIcon, InfoIcon } from "@/components/icons";
import { AttentionChip, PANE } from "./InboxParts";

/**
 * The detail pane before anything is chosen. For messages it also explains the three reasons a
 * conversation can wait for you, so the pane teaches the list instead of standing empty.
 */
export function InboxPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const [params] = useSearchParams();
  const raw = params.get("section");
  const section = location.pathname.includes("/comments") || raw === "comments"
    ? "comments"
    : location.pathname.includes("/questions") || raw === "questions"
      ? "questions"
      : "messages";
  const icon = section === "comments" ? <CommentIcon /> : section === "questions" ? <InfoIcon /> : <ChatIcon />;
  return (
    <div className={`${PANE} flex flex-col items-center px-6 py-12 text-center`}>
      <span aria-hidden="true" className="flex size-12 items-center justify-center rounded-2xl bg-assistant text-xl text-action">
        {icon}
      </span>
      <h2 className="mt-4 font-heading text-lg font-semibold tracking-tight text-primary">{t(`convo.select.${section}.title`)}</h2>
      <p className="mt-1 max-w-sm text-body text-secondary">{t(`convo.select.${section}.hint`)}</p>
      {section === "messages" ? (
        <dl className="mt-7 grid w-full max-w-md gap-2 text-left">
          {(["needs_approval", "needs_human", "failed"] as const).map((key) => (
            <div key={key} className="flex flex-col items-start gap-x-3 gap-y-1.5 rounded-xl bg-surface-subtle/70 px-3 py-2.5 sm:flex-row sm:items-center">
              <dt className="shrink-0 sm:w-36"><AttentionChip attention={key} sample /></dt>
              <dd className="min-w-0 flex-1 text-metadata text-secondary">{t(`convo.legend.${key}`)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
