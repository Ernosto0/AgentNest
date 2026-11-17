import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ManagementSummary } from "./ManagementSummary";

describe("management confirmation preview", () => {
  it("shows both local times and their timezone before a reschedule", () => {
    render(<ManagementSummary action="command.reschedule_content" summary={{ label: "Story", old_formatted: "16 Kas 10:00", new_formatted: "16 Kas 19:00", timezone: "Europe/Istanbul" }} />);
    expect(screen.getByTestId("change-from")).toHaveTextContent("16 Kas 10:00");
    expect(screen.getByTestId("change-to")).toHaveTextContent("16 Kas 19:00");
    expect(screen.getByText(/Europe\/Istanbul/)).toBeInTheDocument();
  });
  it("shows the exact automatic resume time for a pause", () => {
    render(<ManagementSummary action="command.pause_agent" summary={{ resume_at: "17 Kas 09:00", timezone: "Europe/Istanbul" }} />);
    expect(screen.getByText(/17 Kas 09:00/)).toBeInTheDocument();
    expect(screen.getByText(/Europe\/Istanbul/)).toBeInTheDocument();
    expect(screen.queryByTestId("change-from")).toBeNull();
  });
});
