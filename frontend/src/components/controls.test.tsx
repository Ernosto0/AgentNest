import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { TextField } from "./TextField";
import { ChoiceField, SelectField, TextAreaField } from "./FormFields";
import { ErrorSummary, Notice, Skeleton, Toast } from "./Feedback";
import { Pagination } from "./Pagination";

describe("shared forms and feedback", () => {
  it("keeps caller IDs, descriptions and linked inline validation", () => {
    render(<><p id="external">External context</p><TextField id="email" label="Email" hint="Work address" error="Enter an address" aria-describedby="external" defaultValue="retained" /></>);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("id", "email");
    expect(input).toHaveAccessibleDescription("External context Work address Enter an address");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveValue("retained");
  });

  it("generates a labelled ID, respects readonly and removes obsolete error descriptions", () => {
    const { rerender } = render(<TextField label="Name" hint="Keep this" error="Required" readOnly value="Example" />);
    const input = screen.getByLabelText("Name");
    expect(input).toHaveAccessibleDescription("Keep this Required");
    expect(input).toHaveAttribute("readonly");
    rerender(<TextField label="Name" hint="Keep this" readOnly value="Example" />);
    expect(input).toHaveAccessibleDescription("Keep this");
    expect(input).not.toHaveAttribute("aria-invalid");
  });

  it("preserves native select and textarea editing semantics with linked feedback", async () => {
    const user = userEvent.setup();
    render(<><SelectField label="Language" hint="Reply language" error="Review selection" defaultValue="tr"><option value="tr">Turkish</option><option value="en">English</option></SelectField><TextAreaField label="Message" hint="Private draft" defaultValue="Saved" /></>);
    const select = screen.getByRole("combobox", { name: "Language" });
    expect(select).toHaveAccessibleDescription("Reply language Review selection");
    await user.selectOptions(select, "en");
    expect(select).toHaveValue("en");
    const textarea = screen.getByRole("textbox", { name: "Message" });
    await user.type(textarea, " draft");
    expect(textarea).toHaveValue("Saved draft");
    expect(textarea).toHaveAccessibleDescription("Private draft");
  });

  it("keeps checkbox label interaction and native radio groups", async () => {
    const user = userEvent.setup();
    render(<><ChoiceField label="Remember" hint="Optional" /><ChoiceField type="radio" name="choice" label="First" value="one" /><ChoiceField type="radio" name="choice" label="Second" value="two" /></>);
    await user.click(screen.getByText("Remember"));
    expect(screen.getByRole("checkbox", { name: "Remember" })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "First" }));
    await user.click(screen.getByRole("radio", { name: "Second" }));
    expect(screen.getByRole("radio", { name: "First" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Second" })).toBeChecked();
  });

  it("defaults to a nonsubmit button and prevents duplicate actions while pending", async () => {
    const click = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<Button onClick={click}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("type", "button");
    await user.click(button);
    rerender(<Button onClick={click} pending disabledReason="Saving the current version">Save</Button>);
    await user.click(button);
    expect(click).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAccessibleDescription("Saving the current version");
  });

  it("validation summary moves focus to the invalid field without changing its value", async () => {
    const user = userEvent.setup();
    render(<><ErrorSummary title="Review errors" errors={[{ id: "price", message: "Check the price" }]} /><TextField label="Price" id="price" defaultValue="10," error="Check the price" /></>);
    await user.click(screen.getByRole("link", { name: "Check the price" }));
    expect(screen.getByLabelText("Price")).toHaveFocus();
    expect(screen.getByLabelText("Price")).toHaveValue("10,");
  });

  it("does not repeatedly announce static notices and keeps loading separate from success", () => {
    const { rerender } = render(<Notice title="Source removed" tone="attention">Review current sources</Notice>);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(<Notice title="Saved" live="polite" tone="success" />);
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    rerender(<Skeleton label="Loading records" />);
    expect(screen.getByRole("status", { name: "Loading records" })).not.toHaveTextContent("Saved");
  });

  it("keeps noncritical feedback dismissible and cursor controls owned by the caller", async () => {
    const user = userEvent.setup();
    const dismiss = vi.fn();
    const next = vi.fn();
    render(<><Toast dismissLabel="Dismiss notice" onDismiss={dismiss}>Copied</Toast><Pagination label="Results" previousLabel="Previous" nextLabel="Next" onNext={next} /></>);
    expect(screen.getByRole("status")).toHaveTextContent("Copied");
    await user.click(screen.getByRole("button", { name: "Dismiss notice" }));
    expect(dismiss).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(next).toHaveBeenCalledOnce();
  });
});
