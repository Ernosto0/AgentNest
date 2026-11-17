import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BrandSection } from "./BrandSection";

const state = vi.hoisted(() => ({ role: "owner", mutate: vi.fn(), reset: vi.fn() }));
vi.mock("@/features/workspaces/context", () => ({ useCurrentWorkspace: () => ({ workspace: { id: "ws-brand" }, role: state.role }) }));
vi.mock("./hooks", () => ({
  useBrand: () => ({ data: { primary_color: "#123456", accent_color: "#abcdef", logo_media_asset_id: null, is_default: true }, error: null }),
  useSaveBrand: () => ({ mutate: state.mutate, reset: state.reset, isPending: false, isSuccess: false, error: null }),
}));
vi.mock("@/features/content/MediaUpload", () => ({ MediaUpload: ({ disabled, onUploaded }: { disabled: boolean; onUploaded: (asset: { id: string }) => void }) => <button type="button" disabled={disabled} onClick={() => onUploaded({ id: "logo-id" })}>Upload logo</button> }));

beforeEach(() => { state.role = "owner"; state.mutate.mockReset(); });

describe("workspace brand", () => {
  it("renders both colours and logo upload", () => {
    render(<BrandSection />);
    expect(screen.getByLabelText("Ana renk")).toHaveValue("#123456");
    expect(screen.getByLabelText("Vurgu rengi")).toHaveValue("#abcdef");
    expect(screen.getByRole("button", { name: "Upload logo" })).toBeEnabled();
  });

  it("saves normalized colours and the uploaded logo as manager", async () => {
    state.role = "manager";
    render(<BrandSection />);
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("Ana renk"));
    await user.type(screen.getByLabelText("Ana renk"), "#AABBCC");
    await user.click(screen.getByRole("button", { name: "Upload logo" }));
    await user.click(screen.getByRole("button", { name: "Markayı kaydet" }));
    expect(state.mutate).toHaveBeenCalledWith({ primary_color: "#aabbcc", accent_color: "#abcdef", logo_media_asset_id: "logo-id" });
  });

  it("rejects bad hex without saving", async () => {
    render(<BrandSection />);
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("Ana renk"));
    await user.type(screen.getByLabelText("Ana renk"), "red");
    await user.click(screen.getByRole("button", { name: "Markayı kaydet" }));
    expect(screen.getByRole("alert")).toHaveTextContent("hex");
    expect(state.mutate).not.toHaveBeenCalled();
  });

  it("keeps staff read-only", () => {
    state.role = "staff";
    render(<BrandSection />);
    expect(screen.getByLabelText("Ana renk")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Upload logo" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Markayı kaydet" })).not.toBeInTheDocument();
  });

  it("clears a staged logo before saving", async () => {
    render(<BrandSection />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Upload logo" }));
    await user.click(screen.getByRole("button", { name: "Logoyu kaldır" }));
    await user.click(screen.getByRole("button", { name: "Markayı kaydet" }));
    expect(state.mutate).toHaveBeenCalledWith({ primary_color: "#123456", accent_color: "#abcdef", logo_media_asset_id: null });
  });
});
