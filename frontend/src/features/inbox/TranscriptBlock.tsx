import { useTranslation } from "react-i18next";
import type { ReplyDraft } from "@/api/types";
import { AlertIcon, MicIcon, SpinnerIcon } from "@/components/icons";

type TranscriptStatus = "pending" | "succeeded" | "failed";

/** The language code shown to the owner: Turkish, English, or "another language". */
function useLanguageLabel(language: string | null | undefined): string | null {
  const { t } = useTranslation();
  if (!language) return null;
  return t(`convo.transcript.languages.${language === "tr" || language === "en" ? language : "other"}`);
}

/**
 * What a customer said in a voice note, as written down by the machine. It is always labelled
 * "Transcript (automatic)" with its language, so it is never mistaken for the customer's own typed
 * words. The audio is not stored, so there is no player: the owner listens in Instagram.
 *
 * `status` defaults to "succeeded" for the approval view, where only finished transcripts exist.
 */
export function TranscriptBlock({
  text,
  language,
  status = "succeeded",
  reasonCode,
  showListenHint = false,
}: {
  text: string | null;
  language: string | null | undefined;
  status?: TranscriptStatus;
  reasonCode?: string | null;
  showListenHint?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const languageLabel = useLanguageLabel(language);
  const spoken = language === "tr" || language === "en" ? language : undefined;

  if (status === "pending") {
    return (
      <p
        role="status"
        data-testid="transcript-pending"
        className="mt-2 inline-flex items-center gap-2 text-metadata text-secondary"
      >
        <SpinnerIcon aria-hidden="true" className="shrink-0 animate-spin" />
        {t("convo.transcript.pending")}
      </p>
    );
  }
  if (status === "failed") {
    const reason = reasonCode && i18n.exists(`convo.transcript.reason.${reasonCode}`) ? t(`convo.transcript.reason.${reasonCode}`) : null;
    return (
      <div data-testid="transcript-failed" className="mt-2 flex items-start gap-2 text-metadata text-secondary">
        <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
        <p>
          {t("convo.transcript.failed")}
          {reason ? <span> {reason}</span> : null}
          <span className="sr-only"> {reasonCode}</span>
        </p>
      </div>
    );
  }
  return (
    <figure
      data-testid="transcript"
      aria-label={t("convo.transcript.title")}
      className="mt-2 rounded-xl border border-dashed border-action/30 bg-surface-subtle px-3 py-2.5 text-primary"
    >
      <figcaption className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-semibold text-secondary">
        <MicIcon aria-hidden="true" className="shrink-0 text-sm" />
        <span>{t("convo.transcript.title")}</span>
        {languageLabel ? (
          <span className="rounded-full border border-border bg-surface px-2 py-0.5 font-medium" data-testid="transcript-language">
            {languageLabel}
          </span>
        ) : null}
      </figcaption>
      {text ? (
        <blockquote lang={spoken} className="mt-1.5 text-[0.9375rem] leading-6 break-words whitespace-pre-wrap">
          {text}
        </blockquote>
      ) : (
        <p className="mt-1.5 text-metadata text-secondary italic">{t("convo.transcript.erased")}</p>
      )}
      <p className="mt-1.5 text-xs text-secondary">
        {t("convo.transcript.mayHaveErrors")}
        {showListenHint ? <> {t("convo.transcript.listenInInstagram")}</> : null}
      </p>
    </figure>
  );
}

/**
 * The voice notes a reply was written from, for the inbox draft and the approval view: each
 * transcript labelled as automatic, and a line saying why a person must check it.
 */
export function DraftTranscripts({ transcripts }: { transcripts: ReplyDraft["transcripts"] }) {
  const { t } = useTranslation();
  if (!transcripts || transcripts.length === 0) return null;
  return (
    <div data-testid="draft-transcripts">
      <p className="text-xs font-semibold text-secondary">{t("convo.transcript.basis")}</p>
      {transcripts.map((item) => (
        <TranscriptBlock key={item.message_id} text={item.text} language={item.language} />
      ))}
    </div>
  );
}
