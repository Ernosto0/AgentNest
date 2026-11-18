import { useTranslation } from "react-i18next";
import type { ChatMessage } from "@/api/types";
import { AlertIcon, ImageIcon, SpinnerIcon } from "@/components/icons";

export type ImageDescription = NonNullable<ChatMessage["image_descriptions"]>[number];

/**
 * What a customer's photo or screenshot shows, as written by a machine, for the owner only.
 * It is always labelled "What the customer sent (automatic)", so it is never mistaken for the
 * customer's own words. The text read from the picture is customer content: it is shown as plain
 * text in a quoted block, never as an instruction, and a warning appears when it looks like one.
 * The picture is not stored, so there is nothing to show here: the owner opens it in Instagram.
 */
export function ImageDescriptionBlock({
  item,
  position,
  count,
}: {
  item: ImageDescription;
  /** 1-based place among the described images of the message, shown when there are several. */
  position: number;
  count: number;
}) {
  const { t, i18n } = useTranslation();
  const numbered = count > 1 ? t("convo.imageDescription.photoNumber", { n: position }) : null;

  if (item.status === "pending") {
    return (
      <p
        role="status"
        data-testid="image-description-pending"
        className="mt-2 inline-flex items-center gap-2 text-metadata text-secondary"
      >
        <SpinnerIcon aria-hidden="true" className="shrink-0 animate-spin" />
        {t("convo.imageDescription.pending")}
        {numbered ? <span> ({numbered})</span> : null}
      </p>
    );
  }
  if (item.status === "failed") {
    const code = item.reason_code;
    const reason = code && i18n.exists(`convo.imageDescription.reason.${code}`) ? t(`convo.imageDescription.reason.${code}`) : null;
    return (
      <div data-testid="image-description-failed" className="mt-2 flex items-start gap-2 text-metadata text-secondary">
        <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
        <p>
          {numbered ? <span>{numbered}: </span> : null}
          {t("convo.imageDescription.failed")}
          {reason ? <span> {reason}</span> : null}
          <span className="sr-only"> {code}</span>
        </p>
      </div>
    );
  }
  const kind = item.looks_like ?? "other";
  return (
    <figure
      data-testid="image-description"
      aria-label={t("convo.imageDescription.title")}
      className="mt-2 rounded-xl border border-dashed border-action/30 bg-surface-subtle px-3 py-2.5 text-primary"
    >
      <figcaption className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-semibold text-secondary">
        <ImageIcon aria-hidden="true" className="shrink-0 text-sm" />
        <span>{t("convo.imageDescription.title")}</span>
        {numbered ? <span className="font-medium">· {numbered}</span> : null}
        <span className="rounded-full border border-border bg-surface px-2 py-0.5 font-medium" data-testid="image-description-kind">
          {t(`convo.imageDescription.kinds.${kind}`)}
        </span>
      </figcaption>
      {item.description ? (
        <p dir="auto" className="mt-1.5 text-[0.9375rem] leading-6 break-words whitespace-pre-wrap">{item.description}</p>
      ) : (
        <p className="mt-1.5 text-metadata text-secondary italic">{t("convo.imageDescription.erased")}</p>
      )}
      {item.visible_text ? (
        <div className="mt-2" data-testid="image-description-text">
          <p className="text-xs font-semibold text-secondary">{t("convo.imageDescription.visibleText")}</p>
          <blockquote dir="auto" className="mt-1 border-s-2 border-border ps-2.5 text-[0.9375rem] leading-6 break-words whitespace-pre-wrap">
            {item.visible_text}
          </blockquote>
        </div>
      ) : null}
      {item.injection_suspected ? (
        <p role="note" data-testid="image-description-warning" className="mt-2 flex items-start gap-2 text-xs font-medium text-attention">
          <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
          {t("convo.imageDescription.injection")}
        </p>
      ) : null}
      <p className="mt-1.5 text-xs text-secondary">
        {t("convo.imageDescription.mayBeWrong")} {t("convo.imageDescription.openInInstagram")}
      </p>
    </figure>
  );
}
