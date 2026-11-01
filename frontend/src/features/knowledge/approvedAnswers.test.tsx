import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApprovedAnswer, Me } from "@/api/types";
import { ME, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;

function staffMe(): Me {
  return {
    ...ME,
    memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" } : m)),
  };
}

const mockAnswer1: ApprovedAnswer = {
  id: "ans-1",
  title: "Aylık Üyelik Bilgisi",
  intent: "pricing",
  language: "tr",
  status: "active",
  example_questions: ["Aylık ne kadar?", "Üyelik ücreti nedir?"],
  answer_template: "Aylık salon üyeliğimiz {{fact:pricing.membership_monthly}}'dir. Detaylar için bekleriz!",
  created_from_message_id: null,
  version: 1,
  updated_at: "2026-10-25T12:00:00Z",
};

const mockAnswerReview: ApprovedAnswer = {
  id: "ans-2",
  title: "Ders Programı",
  intent: "hours",
  language: "tr",
  status: "needs_review",
  example_questions: ["Hafta sonu açık mısınız?"],
  answer_template: "Hafta sonu çalışma saatlerimiz: {{fact:hours.weekly}}.",
  created_from_message_id: "msg-123",
  version: 2,
  updated_at: "2026-10-26T14:00:00Z",
};

function routes(extra: Record<string, (req: RecordedRequest) => Response | Promise<Response>> = {}, me: Me = ME) {
  return {
    "GET /api/v1/meta": () =>
      json({
        product_name: "AgentNest",
        demo_tools_enabled: true,
        llm_mode: "fake",
        supported_locales: ["tr", "en"],
        instagram_providers: ["mock"],
        mock_requires_demo_workspace: false,
      }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/approved-answers`]: () => json({ items: [mockAnswer1, mockAnswerReview], next_cursor: null }),
    ...extra,
  };
}

describe("ApprovedAnswers", () => {
  it("renders approved answers with intent badges, placeholders, and needs_review status", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/answers`);

    // Title and back link
    expect(await screen.findByRole("heading", { name: "Onaylı yanıtlar" })).toBeInTheDocument();
    expect(screen.getByText("← İşletme bilgilerine dön")).toBeInTheDocument();

    // Answer 1
    expect(await screen.findByText("Aylık Üyelik Bilgisi")).toBeInTheDocument();
    expect(screen.getByText('"Aylık ne kadar? · Üyelik ücreti nedir?"')).toBeInTheDocument();
    expect(screen.getByText("{{fact:pricing.membership_monthly}}")).toBeInTheDocument();

    // Answer 2 with needs_review badge
    expect(screen.getByText("Ders Programı")).toBeInTheDocument();
    expect(screen.getByText("Gözden geçirilmeli")).toBeInTheDocument();
    expect(screen.getByText("{{fact:hours.weekly}}")).toBeInTheDocument();
  });

  it("shows empty state when no approved answers exist", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/approved-answers`]: () => json({ items: [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/answers`);

    expect(await screen.findByText("Henüz onaylı yanıt yok.")).toBeInTheDocument();
  });

  it("restricts staff from creating or archiving approved answers", async () => {
    mockApi(routes({}, staffMe()));
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/answers`);

    expect(await screen.findByRole("heading", { name: "Onaylı yanıtlar" })).toBeInTheDocument();

    // Staff note is shown
    expect(
      screen.getByText("Yalnızca işletme sahipleri ve yöneticiler onaylı yanıt oluşturabilir veya arşivleyebilir."),
    ).toBeInTheDocument();

    // Creation form is hidden
    expect(screen.queryByRole("heading", { name: "Yeni onaylı yanıt" })).not.toBeInTheDocument();

    // Archive buttons are hidden
    expect(screen.queryByRole("button", { name: "Arşivle" })).not.toBeInTheDocument();
  });

  it("allows owner to create a new approved answer", async () => {
    const user = userEvent.setup();
    let createdBody: Record<string, unknown> | null = null;

    mockApi(
      routes({
        [`POST ${BASE}/approved-answers`]: (req) => {
          createdBody = req.body as Record<string, unknown>;
          return json({
            id: "ans-new",
            title: createdBody.title as string,
            intent: createdBody.intent as string,
            language: createdBody.language as string,
            status: "active",
            example_questions: createdBody.example_questions as string[],
            answer_template: createdBody.answer_template as string,
            created_from_message_id: null,
            version: 1,
            updated_at: "2026-11-01T12:00:00Z",
          });
        },
      }),
    );

    renderApp(`/w/${WS_GOLKENT}/more/knowledge/answers`);

    expect(await screen.findByRole("heading", { name: "Yeni onaylı yanıt" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Başlık"), "İletişim Bilgisi");
    await user.type(screen.getByLabelText("Müşterilerin sorduğu bir soru"), "Telefon numaranız nedir?");
    fireEvent.change(screen.getByLabelText("Yanıt"), {
      target: { value: "Bize {{fact:contact.phone}} numarasından ulaşabilirsiniz." },
    });

    const saveButton = screen.getByRole("button", { name: "Yanıtı kaydet" });
    expect(saveButton).toBeEnabled();
    await user.click(saveButton);

    await waitFor(() => {
      expect(createdBody).toMatchObject({
        title: "İletişim Bilgisi",
        intent: "faq",
        language: "tr",
        example_questions: ["Telefon numaranız nedir?"],
        answer_template: "Bize {{fact:contact.phone}} numarasından ulaşabilirsiniz.",
      });
    });
  });

  it("allows owner to archive an approved answer", async () => {
    const user = userEvent.setup();
    let archivedId: string | null = null;

    mockApi(
      routes({
        [`PATCH ${BASE}/approved-answers/ans-1`]: () => {
          archivedId = "ans-1";
          return json({ ...mockAnswer1, status: "archived" });
        },
      }),
    );

    renderApp(`/w/${WS_GOLKENT}/more/knowledge/answers`);

    const archiveButtons = await screen.findAllByRole("button", { name: "Arşivle" });
    expect(archiveButtons.length).toBeGreaterThan(0);
    await user.click(archiveButtons[0]!);

    await waitFor(() => {
      expect(archivedId).toBe("ans-1");
    });
  });
});
