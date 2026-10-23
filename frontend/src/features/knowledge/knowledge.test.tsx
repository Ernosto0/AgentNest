import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Me } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, candidate, fact, templateItem, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;

function staffMe(): Me {
  return {
    ...ME,
    memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" } : m)),
  };
}

function routes(extra: Record<string, () => Response> = {}, me: Me = ME) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: [], next_cursor: null }),
    [`GET ${BASE}/facts/template`]: () => json([]),
    [`GET ${BASE}/fact-candidates`]: () => json({ items: [], next_cursor: null }),
    ...extra,
  };
}

const student = fact({
  id: "f0000000-0000-4000-8000-000000000002",
  key: "pricing.student_monthly",
  label: { tr: "Öğrenci aylık üyelik", en: "Student monthly membership" },
  display: "4.500 ₺ / ay",
  status: "unverified",
  state: "unverified",
  usable: false,
  last_verified_at: null,
});

const pricingTemplate = [
  templateItem({ status: "verified" }),
  templateItem({
    identifier: "pricing.student_monthly",
    key: "pricing.student_monthly",
    label: { tr: "Öğrenci aylık üyelik", en: "Student monthly membership" },
    status: "unverified",
  }),
  templateItem({
    identifier: "pricing.single_session",
    key: "pricing.single_session",
    label: { tr: "Tek seans", en: "Single session" },
    status: "missing",
    required_for: "ready",
  }),
];

const pricingRoutes = {
  [`GET ${BASE}/facts`]: () => json({ items: [fact(), student], next_cursor: null }),
  [`GET ${BASE}/facts/template`]: () => json(pricingTemplate),
};

describe("Home readiness card", () => {
  it("shows the level and the open items with deep links; unavailable steps are plain text", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}`);

    expect(await screen.findByTestId("readiness-level")).toHaveTextContent("Taslaklar için hazır");
    const open = within(screen.getByRole("heading", { name: "Hazırlık durumu" }).closest("div")!.parentElement!);
    const booking = open.getByRole("link", { name: /Rezervasyon talimatı/ });
    expect(booking).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/knowledge/booking`);
    // The account step and the automation review share one screen (Phase 4).
    const account = open.getByRole("link", { name: /Instagram hesabı bağlı/ });
    expect(account).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/automation`);
    expect(open.getByText("Henüz bağlı değil")).toBeInTheDocument();
    expect(open.queryByText("İşletme adı")).toBeNull(); // satisfied items are not repeated
  });
});

describe("category screen", () => {
  it("lists facts with status, source and date, and marks missing template items", async () => {
    mockApi(routes(pricingRoutes));
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/pricing`);

    const monthly = await screen.findByTestId("fact-pricing.membership_monthly");
    expect(within(monthly).getByText("6.000 ₺ / ay")).toBeInTheDocument();
    expect(within(monthly).getByText("Doğrulandı")).toBeInTheDocument();
    expect(monthly).toHaveTextContent("12 Eki 2026 tarihinde doğrulandı");
    expect(monthly).toHaveTextContent("Demo verisi");

    const unverified = screen.getByTestId("fact-pricing.student_monthly");
    expect(within(unverified).getByText("Doğrulanmamış")).toBeInTheDocument();
    expect(unverified).toHaveTextContent("Doğrulanana kadar hiçbir yerde kullanılmaz.");

    const missing = screen.getByTestId("missing-pricing.single_session");
    expect(within(missing).getByText("Eksik")).toBeInTheDocument();
    expect(missing).toHaveTextContent("Otomasyonun açılabilmesi için gerekli.");
  });

  it("verifies an unverified fact with its current version", async () => {
    const user = userEvent.setup();
    const requests = mockApi(
      routes({
        ...pricingRoutes,
        [`POST ${BASE}/facts/${student.id}/verify`]: () =>
          json({ ...student, status: "verified", state: "verified", usable: true, current_version: 2 }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/pricing`);

    const card = await screen.findByTestId("fact-pricing.student_monthly");
    await user.click(within(card).getByRole("button", { name: "Doğrula" }));

    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/verify"))).toBe(true));
    const verify = requests.find((r) => r.path.endsWith("/verify"));
    expect(verify?.body).toEqual({ expected_version: 1 });
    expect(verify?.headers.get("x-csrf-token")).toBe("csrf-token-for-tests");
  });

  it("hides verification from staff and words editing as a suggestion", async () => {
    mockApi(routes(pricingRoutes, staffMe()));
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/pricing`);

    const card = await screen.findByTestId("fact-pricing.student_monthly");
    expect(within(card).queryByRole("button", { name: "Doğrula" })).toBeNull();
    expect(within(card).getByRole("button", { name: "Değişiklik öner" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Düzenle" })).toBeNull();
  });

  it("shows a history of immutable versions", async () => {
    const user = userEvent.setup();
    mockApi(
      routes({
        ...pricingRoutes,
        [`GET ${BASE}/facts/${fact().id}/versions`]: () =>
          json({
            items: [
              {
                version: 2, value: {}, display: "7.000 ₺ / ay", status: "verified", valid_from: null,
                valid_until: null, source_type: "owner_entry", source_ref: null, actor_type: "user",
                actor_name: "Demo Sahip", reason: "Zam", change_kind: "value_changed",
                created_at: "2026-10-15T09:00:00Z",
              },
              {
                version: 1, value: {}, display: "6.000 ₺ / ay", status: "verified", valid_from: null,
                valid_until: null, source_type: "seed", source_ref: null, actor_type: "system",
                actor_name: null, reason: null, change_kind: "created", created_at: "2026-10-12T09:00:00Z",
              },
            ],
            next_cursor: null,
          }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/pricing`);
    const card = await screen.findByTestId("fact-pricing.membership_monthly");
    await user.click(within(card).getByRole("button", { name: "Geçmiş" }));

    const dialog = await screen.findByRole("dialog", { name: /Geçmiş: Aylık üyelik/ });
    expect(await within(dialog).findByText("Sürüm 2")).toBeInTheDocument();
    expect(within(dialog).getByText("Sürüm 1")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Demo Sahip");
    expect(dialog).toHaveTextContent("Zam");
  });
});

describe("fact editor", () => {
  async function openEditor(me: Me = ME, extra: Record<string, () => Response> = {}) {
    const user = userEvent.setup();
    const requests = mockApi(routes({ ...pricingRoutes, ...extra }, me));
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/pricing`);
    const card = await screen.findByTestId("fact-pricing.membership_monthly");
    await user.click(within(card).getByRole("button", { name: /Düzenle|Değişiklik öner/ }));
    const dialog = await screen.findByRole("dialog");
    return { user, requests, dialog };
  }

  it("previews the formatted amount and saves the canonical value", async () => {
    const { user, requests, dialog } = await openEditor(ME, {
      [`PATCH ${BASE}/facts/${fact().id}`]: () => json(fact({ current_version: 2 })),
    });
    const amount = within(dialog).getByLabelText("Tutar (TRY)");
    expect(amount).toHaveValue("6000");
    await user.clear(amount);
    await user.type(amount, "7.000");

    expect(within(dialog).getByText("Müşteriler şunu görecek: 7.000 ₺")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Kaydet" }));

    await waitFor(() => expect(requests.some((r) => r.method === "PATCH")).toBe(true));
    expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({
      expected_version: 1,
      value: { amount: "7000.00", currency: "TRY", unit: "month" },
      reason: null,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("asks which amount is meant when the notation is unclear, and will not save before an answer", async () => {
    const { user, dialog } = await openEditor();
    const amount = within(dialog).getByLabelText("Tutar (TRY)");
    await user.clear(amount);
    await user.type(amount, "7,000");

    expect(within(dialog).getByText(/birden fazla tutar anlamına gelebilir/)).toBeInTheDocument();
    const save = within(dialog).getByRole("button", { name: "Kaydet" });
    expect(save).toBeDisabled();
    await user.click(within(dialog).getByRole("radio", { name: "7.000 ₺" }));
    expect(save).toBeEnabled();
  });

  it("rejects text that is not an amount without enabling save", async () => {
    const { user, dialog } = await openEditor();
    const amount = within(dialog).getByLabelText("Tutar (TRY)");
    await user.clear(amount);
    await user.type(amount, "çok pahalı");
    expect(within(dialog).getByText("Bu bir tutara benzemiyor.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Kaydet" })).toBeDisabled();
  });

  it("tells staff that their change becomes a suggestion", async () => {
    const { user, dialog } = await openEditor(staffMe(), {
      [`PATCH ${BASE}/facts/${fact().id}`]: () => json(candidate({ relation: "contest" }), 202),
    });
    expect(dialog).toHaveTextContent("öneri olarak gönderilir");
    const amount = within(dialog).getByLabelText("Tutar (TRY)");
    await user.clear(amount);
    await user.type(amount, "7500");
    await user.click(within(dialog).getByRole("button", { name: "Değer öner" }));
    expect(await within(dialog).findByRole("status")).toHaveTextContent("öneri olarak gönderildi");
  });

  it("shows the stale-version conflict in plain language and keeps the dialog open", async () => {
    const { user, dialog } = await openEditor(ME, {
      [`PATCH ${BASE}/facts/${fact().id}`]: () =>
        new Response(
          JSON.stringify({ type: "about:blank", title: "Conflict", status: 409, code: "FACT_VERSION_CONFLICT", params: { current_version: 3 }, request_id: "r1" }),
          { status: 409, headers: { "content-type": "application/problem+json" } },
        ),
    });
    const amount = within(dialog).getByLabelText("Tutar (TRY)");
    await user.clear(amount);
    await user.type(amount, "7000");
    await user.click(within(dialog).getByRole("button", { name: "Kaydet" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Bu bilgi siz düzenlerken başka biri tarafından değiştirildi.",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("suggestions", () => {
  it("explains a discrepancy with the source and the verified value, and lets the owner reject it", async () => {
    const user = userEvent.setup();
    const requests = mockApi(
      routes({
        [`GET ${BASE}/fact-candidates`]: () => json({ items: [candidate()], next_cursor: null }),
        [`POST ${BASE}/fact-candidates/${candidate().id}/reject`]: () => json({ ...candidate(), status: "rejected" }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/suggestions`);

    const card = await screen.findByTestId("candidate-pricing.membership_monthly");
    expect(card).toHaveTextContent(
      "Yapıştırdığınız metin 5.500 ₺ / ay diyor, ama doğrulanmış değeriniz 6.000 ₺ / ay.",
    );
    expect(card).toHaveTextContent("Instagram bio: Aylık üyelik 5.500 TL");
    await user.click(within(card).getByRole("button", { name: "Mevcut değeri koru" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/reject"))).toBe(true));
  });

  it("names the team member behind a contest and offers the proposed value for acceptance", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/fact-candidates`]: () =>
          json({
            items: [candidate({ relation: "contest", source_type: "staff_proposal", proposed_by_name: "Elif", proposed_display: "7.500 ₺ / ay", source_excerpt: null })],
            next_cursor: null,
          }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/suggestions`);
    const card = await screen.findByTestId("candidate-pricing.membership_monthly");
    expect(card).toHaveTextContent("Elif 7.500 ₺ / ay değerini öneriyor (mevcut değer: 6.000 ₺ / ay).");
    expect(within(card).getByRole("button", { name: "7.500 ₺ / ay değerini kullan" })).toBeInTheDocument();
  });

  it("lets staff read suggestions but not decide them", async () => {
    mockApi(
      routes(
        { [`GET ${BASE}/fact-candidates`]: () => json({ items: [candidate()], next_cursor: null }) },
        staffMe(),
      ),
    );
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/suggestions`);
    await screen.findByTestId("candidate-pricing.membership_monthly");
    expect(screen.queryByRole("button", { name: "Mevcut değeri koru" })).toBeNull();
    expect(screen.getByText(/yalnızca işletme sahibi veya yönetici/)).toBeInTheDocument();
  });

  it("shows an empty state that explains when suggestions appear", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/suggestions`);
    expect(await screen.findByText("İncelenecek öneri yok")).toBeInTheDocument();
  });
});

describe("overview", () => {
  it("shows one row per category with counts and the number of waiting suggestions", async () => {
    mockApi(
      routes({
        ...pricingRoutes,
        [`GET ${BASE}/fact-candidates`]: () => json({ items: [candidate()], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/knowledge`);

    const pricing = await screen.findByRole("link", { name: /Fiyatlar/ });
    expect(pricing).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/knowledge/pricing`);
    expect(pricing).toHaveTextContent("Doğrulandı1");
    expect(pricing).toHaveTextContent("Doğrulanmamış1");
    expect(pricing).toHaveTextContent("Eksik1");
    expect(await screen.findByText("1 öneri sizi bekliyor")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Diğer bilgiler/ })).toBeInTheDocument(); // custom facts
  });

  it("is reachable from More", async () => {
    const user = userEvent.setup();
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more`);
    await user.click(await screen.findByRole("link", { name: /İşletme bilgileri/ }));
    expect(await screen.findByRole("heading", { name: "İşletme bilgileri" })).toBeInTheDocument();
  });

  it("answers an unknown category with the not-found page", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/bogus`);
    expect(await screen.findByRole("heading", { name: "Bulunamadı" })).toBeInTheDocument();
  });
});
