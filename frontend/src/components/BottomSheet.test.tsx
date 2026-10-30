import { useRef, useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BottomSheet } from "./BottomSheet";
import { Button } from "./Button";
import { TextField } from "./TextField";

function Example({ nested = false, dismissible = true }: { nested?: boolean; dismissible?: boolean }) {
  const [open, setOpen] = useState(false);
  const [child, setChild] = useState(false);
  const initial = useRef<HTMLInputElement>(null);
  return <><button onClick={() => setOpen(true)}>Open</button><button>Background</button>{open ? <BottomSheet title="Parent sheet" description="Review the current subject" onClose={() => setOpen(false)} dismissible={dismissible} initialFocusRef={initial} footer={<Button onClick={() => setOpen(false)}>Done</Button>}><TextField label="Draft" ref={initial} defaultValue="Keep me" /><button onClick={() => setChild(true)}>Open child</button>{nested && child ? <BottomSheet title="Child sheet" onClose={() => setChild(false)}><button>Child action</button></BottomSheet> : null}</BottomSheet> : null}</>;
}

describe("BottomSheet modal behavior", () => {
  it("enters, traps and restores focus, isolates background and locks scrolling", async () => {
    const user = userEvent.setup();
    const { container } = render(<Example />);
    const trigger = screen.getByRole("button", { name: "Open" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Parent sheet" });
    expect(dialog).toHaveAccessibleDescription("Review the current subject");
    expect(screen.getByLabelText("Draft")).toHaveFocus();
    expect(container).toHaveAttribute("inert");
    expect(container).toHaveAttribute("aria-hidden", "true");
    expect(document.body.style.overflow).toBe("hidden");
    within(dialog).getByRole("button", { name: "Done" }).focus();
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "Kapat" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(dialog).getByRole("button", { name: "Done" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
    expect(container).not.toHaveAttribute("inert");
    expect(container).not.toHaveAttribute("aria-hidden");
    expect(document.body.style.overflow).toBe("");
  });

  it("keeps programmatic background focus within the dialog", async () => {
    const user = userEvent.setup();
    render(<Example />);
    const background = screen.getByRole("button", { name: "Background" });
    await user.click(screen.getByRole("button", { name: "Open" }));
    background.focus();
    expect(screen.getByRole("dialog")).toHaveFocus();
  });

  it("closes only the topmost nested sheet and returns focus through both triggers", async () => {
    const user = userEvent.setup();
    render(<Example nested />);
    const trigger = screen.getByRole("button", { name: "Open" });
    await user.click(trigger);
    const childTrigger = screen.getByRole("button", { name: "Open child" });
    await user.click(childTrigger);
    const child = screen.getByRole("dialog", { name: "Child sheet" });
    expect(child).toHaveFocus();
    expect(screen.queryByRole("dialog", { name: "Parent sheet" })).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Child sheet" })).toBeNull();
    expect(childTrigger).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.getByLabelText("Draft")).toHaveValue("Keep me");
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).toBe("");
  });

  it("preserves pre-existing inert/aria-hidden and body scroll styles exactly", () => {
    const background = document.createElement("div");
    background.setAttribute("inert", "existing");
    background.setAttribute("aria-hidden", "false");
    document.body.append(background);
    document.body.style.overflow = "clip";
    const { unmount } = render(<BottomSheet title="Test" onClose={vi.fn()}>Body</BottomSheet>);
    expect(background).toHaveAttribute("aria-hidden", "true");
    unmount();
    expect(background).toHaveAttribute("inert", "existing");
    expect(background).toHaveAttribute("aria-hidden", "false");
    expect(document.body.style.overflow).toBe("clip");
    document.body.style.overflow = "";
    background.remove();
  });

  it("blocks close button, Escape and backdrop while nondismissible", async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<BottomSheet title="Pending" onClose={close} dismissible={false}>Working</BottomSheet>);
    expect(screen.getByRole("button", { name: "Kapat" })).toBeDisabled();
    await user.keyboard("{Escape}");
    fireEvent.click(document.querySelector("[data-sheet-backdrop]")!);
    expect(close).not.toHaveBeenCalled();
  });

  it("uses the latest close handler and closes on backdrop", () => {
    const first = vi.fn();
    const latest = vi.fn();
    const { rerender } = render(<BottomSheet title="Test" onClose={first}>Body</BottomSheet>);
    rerender(<BottomSheet title="Test" onClose={latest}>Body</BottomSheet>);
    fireEvent.click(document.querySelector("[data-sheet-backdrop]")!);
    expect(latest).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();
  });

  it("does not throw when the original trigger is removed", () => {
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    const { unmount } = render(<BottomSheet title="Test" onClose={vi.fn()}>Body</BottomSheet>);
    trigger.remove();
    expect(() => unmount()).not.toThrow();
    expect(document.body.style.overflow).toBe("");
  });

  it("restores an explicit opener even when pointer activation did not focus it", () => {
    const opener = document.createElement("button");
    document.body.append(opener);
    const returnFocusRef = { current: opener };
    const { unmount } = render(<BottomSheet title="Test" onClose={vi.fn()} returnFocusRef={returnFocusRef}>Body</BottomSheet>);
    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });

  it("falls back to prior focus when the explicit opener was removed", () => {
    const opener = document.createElement("button");
    const prior = document.createElement("input");
    document.body.append(opener, prior);
    prior.focus();
    const { unmount } = render(<BottomSheet title="Test" onClose={vi.fn()} returnFocusRef={{ current: opener }}>Body</BottomSheet>);
    opener.remove();
    unmount();
    expect(prior).toHaveFocus();
    prior.remove();
  });
});
