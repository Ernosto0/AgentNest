import { useTranslation } from "react-i18next";
import type { ConversationDetail } from "@/api/types";
import { ImageIcon } from "@/components/icons";
import { ContentMedia } from "@/features/content/ContentMedia";

export type MessageStory = NonNullable<ConversationDetail["messages"][number]["story"]>;

/**
 * The story a customer replied to or mentioned you in. For a story we published it shows the
 * stored picture and text; for any other story only what it is (the provider's story link is
 * short-lived and never shown). It is data about the message, not part of what the customer typed.
 */
export function StoryNote({ story }: { story: MessageStory }) {
  const { t } = useTranslation();
  if (story.kind === "mention") return null; // the message bubble itself says it
  const lines = [story.title, ...story.lines].filter((line): line is string => Boolean(line));
  return (
    <aside
      aria-label={t("convo.story.reply")}
      data-testid="story-note"
      className="mb-1.5 flex max-w-[88%] items-start gap-2.5 rounded-xl border border-border bg-surface-subtle p-2 text-secondary sm:max-w-[78%]"
    >
      {story.known ? (
        <ContentMedia
          item={{ media_asset_id: story.media_asset_id, media_deleted: story.media_deleted }}
          compact
          className="aspect-[9/16] w-10 shrink-0 rounded-md"
        />
      ) : (
        <span className="grid aspect-[9/16] w-10 shrink-0 place-items-center rounded-md bg-surface text-base">
          <ImageIcon aria-hidden="true" />
        </span>
      )}
      <div className="min-w-0 text-metadata">
        <p className="font-semibold text-primary">{t("convo.story.reply")}</p>
        {story.known ? (
          <>
            {lines.length > 0 ? (
              <ul className="mt-0.5 space-y-0.5" aria-label={t("convo.story.lines")}>
                {lines.map((line, index) => (
                  <li key={index} className="break-words">
                    {line}
                  </li>
                ))}
              </ul>
            ) : null}
            {story.expired ? <p className="mt-0.5 italic">{t("convo.story.expired")}</p> : null}
          </>
        ) : (
          <p className="mt-0.5">{t("convo.story.unknown")}</p>
        )}
      </div>
    </aside>
  );
}
