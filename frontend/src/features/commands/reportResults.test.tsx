import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import type { Command } from "@/api/types";
import { CurrentWorkspaceContext } from "@/features/workspaces/context";
import i18n from "@/i18n";
import { command } from "@/test/aiFixtures";
import { WS_GOLKENT, workspace } from "@/test/fixtures";
import { CommandResultCard } from "./CommandResultCard";
import { linkPath } from "./messages";

const CONVERSATION = "c1c1c1c1-0000-4000-8000-000000000001";

afterEach(() => i18n.changeLanguage("tr"));

function show(result: { message_key: string; params: Record<string, unknown>; links: unknown[] }) {
  const cmd: Command = command({ status: "completed", result: result as never });
  return render(
    <MemoryRouter>
      <CurrentWorkspaceContext.Provider value={{ workspace: workspace(WS_GOLKENT), role: "owner" }}>
        <CommandResultCard command={cmd} />
      </CurrentWorkspaceContext.Provider>
    </MemoryRouter>,
  );
}

const summary = (overrides: Record<string, unknown> = {}) => ({
  period: "today",
  inbound_messages: 15,
  conversations: 8,
  replies_sent: 40,
  replies_auto: 13,
  replies_approved: 12,
  replies_by_owner: 14,
  escalations: 7,
  attention_now: 9,
  is_simulated: true,
  ...overrides,
});

describe("query.activity_summary", () => {
  it("names the numbers of the report, links to it and says when they are simulated", () => {
    show({
      message_key: "command.activity_summary",
      params: summary(),
      links: [{ target: "report", date: "2026-01-15" }],
    });
    const result = screen.getByTestId("command-result");
    expect(result).toHaveTextContent(
      "Bugün · gelen mesaj: 15, konuşma: 8, gönderilen yanıt: 40 (otomatik 13, onaylı 12, sizin yazdığınız 14), size yönlendirilen: 7, şu an ilgi bekleyen: 9.",
    );
    expect(within(result).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(result).getByRole("link", { name: "Raporu aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/reports?date=2026-01-15`,
    );
  });

  it("is plain text for real data, in the user's language, and the old basic summary is gone", async () => {
    await i18n.changeLanguage("en");
    show({
      message_key: "command.activity_summary",
      params: summary({ period: "yesterday", is_simulated: false, inbound_messages: 1 }),
      links: [{ target: "report", date: "2026-01-14" }],
    });
    const result = screen.getByTestId("command-result");
    expect(result).toHaveTextContent("Yesterday · messages: 1, conversations: 8, replies sent: 40");
    expect(within(result).queryByTestId("simulated-badge")).toBeNull();
    expect(result).not.toHaveTextContent("Basic summary");
    expect(within(result).getByRole("link", { name: "Open the report" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/reports?date=2026-01-14`,
    );
  });
});

describe("query.explain_failure about a reply", () => {
  const params = {
    status: "failed",
    error_code: "OUTCOME_UNCONFIRMED",
    what: "Yanıtın müşteriye ulaşıp ulaşmadığını doğrulayamadık.",
    next: "Yeniden göndermeden önce Instagram'daki konuşmayı kontrol edin.",
    retryable: false,
    when: "21 Eki 19:05",
    is_simulated: true,
  };

  it("says what happened, when and what to do, with a link to the conversation", () => {
    show({
      message_key: "command.reply_failure",
      params,
      links: [{ target: "inbox", id: CONVERSATION }],
    });
    const result = screen.getByTestId("command-result");
    expect(result).toHaveAttribute("data-kind", "reply-failure");
    expect(result).toHaveTextContent("Yanıt neden iletilmedi?");
    expect(result).toHaveTextContent("Yanıtın müşteriye ulaşıp ulaşmadığını doğrulayamadık.");
    expect(result).toHaveTextContent("Yeniden göndermeden önce Instagram'daki konuşmayı kontrol edin.");
    expect(result).toHaveTextContent("Ne zaman: 21 Eki 19:05");
    expect(result).toHaveTextContent("Otomatik olarak tekrar denenmeyecek.");
    expect(within(result).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(result).getByRole("link", { name: "Konuşmayı aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/inbox/${CONVERSATION}`,
    );
  });

  it("shows no badge for a real operation and no time when the server sent none", () => {
    show({
      message_key: "command.reply_failure",
      params: { ...params, is_simulated: false, when: "" },
      links: [{ target: "inbox", id: CONVERSATION }],
    });
    const result = screen.getByTestId("command-result");
    expect(within(result).queryByTestId("simulated-badge")).toBeNull();
    expect(result).not.toHaveTextContent("Ne zaman");
  });
});

describe("a failed post also says when", () => {
  it("adds the time of the failure", () => {
    show({
      message_key: "command.content_failure",
      params: {
        title: "Salı story'si",
        status: "failed",
        error_code: "MEDIA_REJECTED",
        what: "Instagram görseli işleyemedi.",
        next: "Başka bir görsel seçin.",
        retryable: false,
        is_simulated: false,
        retry_at: null,
        when: "21 Eki 19:00",
      },
      links: [{ target: "content", id: "d0000000-0000-4000-8000-000000000001" }],
    });
    expect(screen.getByTestId("command-result")).toHaveTextContent("Ne zaman: 21 Eki 19:00");
  });
});

describe("linkPath", () => {
  it("opens a report day, today's report, and a conversation", () => {
    expect(linkPath("w1", { target: "report", date: "2026-01-14" })).toBe("/w/w1/more/reports?date=2026-01-14");
    expect(linkPath("w1", { target: "report" })).toBe("/w/w1/more/reports");
    expect(linkPath("w1", { target: "inbox", id: "c1" })).toBe("/w/w1/inbox/c1");
    expect(linkPath("w1", { target: "inbox" })).toBe("/w/w1/inbox");
  });
});
