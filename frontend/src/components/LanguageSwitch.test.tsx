import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useTranslation } from "react-i18next";
import { describe, expect, it, vi } from "vitest";
import { LanguageSwitch } from "./LanguageSwitch";

function Probe() {
  const { t } = useTranslation();
  return <h1>{t("nav.home")}</h1>;
}

describe("LanguageSwitch", () => {
  it("starts in Turkish and marks the active language", () => {
    render(<LanguageSwitch />);
    expect(screen.getByRole("button", { name: "Türkçe" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches every translated string when English is chosen", async () => {
    const user = userEvent.setup();
    render(
      <>
        <LanguageSwitch />
        <Probe />
      </>,
    );
    expect(screen.getByRole("heading")).toHaveTextContent("Ana sayfa");

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("heading")).toHaveTextContent("Home");
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Türkçe" })).toHaveAttribute("aria-pressed", "false");
  });

  it("remembers the choice on the device and updates the document language", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitch />);
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(window.localStorage.getItem("agentnest.language")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });

  it("reports changes so the choice can be saved on the account, but not no-op clicks", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<LanguageSwitch onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Türkçe" })); // already active
    expect(onChange).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "English" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("en");
  });

  it("is a labelled group with touch targets of at least 44 px", () => {
    render(<LanguageSwitch />);
    expect(screen.getByRole("group", { name: "Dil" })).toBeInTheDocument();
    for (const button of screen.getAllByRole("button")) {
      expect(button.className).toContain("min-h-11"); // 2.75rem = 44px
    }
  });
});
