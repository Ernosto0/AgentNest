import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { setLanguage } from "@/i18n";
import { StatusBadge } from "./StatusBadge";
import { STATUS_KEYS } from "./status";

const TR_LABELS: Record<(typeof STATUS_KEYS)[number], string> = {
  draft: "Taslak",
  pending_approval: "Onay bekliyor",
  needs_human: "Size devredildi",
  scheduled: "Zamanlandı",
  on_hold: "Beklemede",
  sending: "Gönderiliyor",
  publishing: "Yayınlanıyor",
  checking: "Kontrol ediliyor",
  sent: "Gönderildi",
  published: "Yayınlandı",
  failed: "Başarısız",
  expired: "Süresi doldu",
};

describe("StatusBadge", () => {
  it.each(STATUS_KEYS)("renders the documented Turkish label and an icon for %s", (status) => {
    const { container } = render(<StatusBadge status={status} />);
    expect(screen.getByText(TR_LABELS[status])).toBeInTheDocument();
    expect(container.querySelector(`[data-status="${status}"]`)).not.toBeNull();
    // Never colour alone: every badge also carries an icon.
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("has a distinct label for every status, in both languages", async () => {
    for (const language of ["tr", "en"] as const) {
      await setLanguage(language);
      const labels = STATUS_KEYS.map((status) => {
        const { container, unmount } = render(<StatusBadge status={status} />);
        const text = container.textContent;
        unmount();
        return text;
      });
      expect(new Set(labels).size).toBe(STATUS_KEYS.length);
    }
  });

  it("never reports success before the outcome is verified (INV-18)", async () => {
    await setLanguage("en");
    // The intermediate states must not read as the final ones.
    for (const status of ["scheduled", "pending_approval", "sending", "publishing", "checking"] as const) {
      const { container, unmount } = render(<StatusBadge status={status} />);
      expect(container.textContent).not.toMatch(/^(Sent|Published)$/);
      unmount();
    }
    render(<StatusBadge status="checking" />);
    expect(screen.getByText("Checking")).toBeInTheDocument();
    expect(screen.queryByText("Sent")).toBeNull();
  });

  it("appends the SİMÜLASYON badge only when simulated", () => {
    const { rerender } = render(<StatusBadge status="sent" simulated />);
    expect(screen.getByTestId("simulated-badge")).toHaveTextContent("SİMÜLASYON");
    expect(screen.getByText("Gönderildi")).toBeInTheDocument(); // modifier, not a replacement
    rerender(<StatusBadge status="sent" />);
    expect(screen.queryByTestId("simulated-badge")).toBeNull();
  });

  it("shows SIMULATED in English", async () => {
    await setLanguage("en");
    render(<StatusBadge status="published" simulated />);
    expect(screen.getByTestId("simulated-badge")).toHaveTextContent("SIMULATED");
    expect(screen.getByText("Published")).toBeInTheDocument();
  });

  it("covers every status with a translation key in both catalogs", async () => {
    for (const language of ["tr", "en"] as const) {
      await setLanguage(language);
      for (const status of STATUS_KEYS) {
        const { container, unmount } = render(<StatusBadge status={status} />);
        expect(container.textContent).not.toContain("status."); // a raw key would leak through
        unmount();
      }
    }
  });
});
