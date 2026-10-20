import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ContentItem, ContentStatus } from "@/api/types";
import i18n, { setLanguage } from "@/i18n";
import { contentItem } from "@/test/contentFixtures";
import { WS_GOLKENT, workspace } from "@/test/fixtures";
import { CurrentWorkspaceContext } from "@/features/workspaces/context";
import { ContentCard } from "./ContentCard";
import { CONTENT_TABS, TAB_STATUSES, contentBadge, tabOf } from "./status";

const ALL_STATUSES: ContentStatus[] = [
  "draft",
  "pending_approval",
  "scheduled",
  "publishing",
  "retry_scheduled",
  "on_hold",
  "published",
  "rejected",
  "failed",
  "cancelled",
];

// 19:05 in Istanbul (UTC+3).
const RETRY_AT = "2026-10-20T16:05:00Z";

const TR_LABEL: Record<ContentStatus, string> = {
  draft: "Taslak",
  pending_approval: "Onay bekliyor",
  scheduled: "Zamanlandı",
  publishing: "Yayınlanıyor",
  retry_scheduled: "Tekrar denenecek 19:05",
  on_hold: "Beklemede",
  published: "Yayınlandı",
  rejected: "Reddedildi",
  failed: "Başarısız",
  cancelled: "İptal edildi",
};

function withStatus(status: ContentStatus): ContentItem {
  return contentItem({
    status,
    operation:
      status === "retry_scheduled"
        ? { status: "retry_wait", attempts: 1, next_attempt_at: RETRY_AT, last_error_code: "PROVIDER_UNAVAILABLE" }
        : null,
  });
}

function renderCard(item: ContentItem) {
  return render(
    <MemoryRouter>
      <CurrentWorkspaceContext.Provider value={{ workspace: workspace(WS_GOLKENT), role: "owner" }}>
        <ContentCard item={item} />
      </CurrentWorkspaceContext.Provider>
    </MemoryRouter>,
  );
}

describe("content tabs (G15)", () => {
  it("lists exactly the documented statuses per tab", () => {
    expect(TAB_STATUSES).toEqual({
      drafts: ["draft", "pending_approval"],
      scheduled: ["scheduled", "publishing", "retry_scheduled"],
      published: ["published"],
      problems: ["on_hold", "failed", "rejected"],
    });
  });

  it("puts every status in at most one tab and hides only cancelled", () => {
    for (const status of ALL_STATUSES) {
      const tabs = CONTENT_TABS.filter((tab) => TAB_STATUSES[tab].includes(status));
      expect(tabs.length).toBe(status === "cancelled" ? 0 : 1);
      expect(tabOf(status)).toBe(tabs[0] ?? null);
    }
  });
});

describe("content status mapping (INV-18)", () => {
  it.each(ALL_STATUSES)("%s reads the documented Turkish label on the card", (status) => {
    renderCard(withStatus(status));
    expect(screen.getByText(TR_LABEL[status])).toBeInTheDocument();
  });

  it("says 'Yayınlandı' only for a published item", () => {
    for (const status of ALL_STATUSES) {
      const { unmount } = renderCard(withStatus(status));
      const claimsPublished = screen.queryByText("Yayınlandı") !== null;
      expect(claimsPublished, status).toBe(status === "published");
      unmount();
    }
  });

  it("says 'Published' only for a published item in English too", async () => {
    await setLanguage("en");
    for (const status of ALL_STATUSES) {
      const { unmount } = renderCard(withStatus(status));
      expect(screen.queryByText("Published") !== null, status).toBe(status === "published");
      unmount();
    }
  });

  it("shows 'Kontrol ediliyor' while a publish attempt has an unknown outcome", () => {
    const item = contentItem({
      status: "publishing",
      operation: { status: "outcome_unknown", attempts: 1, next_attempt_at: null, last_error_code: null },
    });
    renderCard(item);
    expect(screen.getByText("Kontrol ediliyor")).toBeInTheDocument();
    expect(screen.queryByText("Yayınlanıyor")).toBeNull();
    expect(screen.queryByText("Yayınlandı")).toBeNull();
  });

  it("shows 'Yayınlanıyor' for an attempt that is simply running", () => {
    const badge = contentBadge(
      contentItem({
        status: "publishing",
        operation: { status: "in_progress", attempts: 1, next_attempt_at: null, last_error_code: null },
      }),
      i18n.t,
      "tr",
      "Europe/Istanbul",
    );
    expect(badge).toEqual({ status: "publishing" });
  });

  it("says when a retry will happen, in the workspace time zone, and copes with no time", () => {
    const retry = contentItem({
      status: "retry_scheduled",
      operation: { status: "retry_wait", attempts: 1, next_attempt_at: RETRY_AT, last_error_code: null },
    });
    expect(contentBadge(retry, i18n.t, "tr", "Europe/Istanbul")).toEqual({
      status: "retry_scheduled",
      params: { time: "19:05" },
    });
    const noTime = contentBadge(contentItem({ status: "retry_scheduled" }), i18n.t, "tr", "Europe/Istanbul");
    expect(noTime.params?.time).toBe("kısa süre sonra");
  });

  it("appends the SİMÜLASYON badge for a simulated item only", () => {
    const { unmount } = renderCard(contentItem({ is_simulated: true }));
    expect(screen.getByTestId("simulated-badge")).toHaveTextContent("SİMÜLASYON");
    unmount();
    renderCard(contentItem({ is_simulated: false }));
    expect(screen.queryByTestId("simulated-badge")).toBeNull();
  });
});
