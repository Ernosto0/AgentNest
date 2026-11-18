import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import i18n from "@/i18n";
import { contentItem, mediaAsset } from "@/test/contentFixtures";
import { CarouselMedia } from "./CarouselMedia";
import { ContentComposer } from "./ContentComposer";
import { CurrentWorkspaceContext } from "@/features/workspaces/context";
import { workspace, WS_GOLKENT } from "@/test/fixtures";
import { append, CAROUSEL_CODES, move, remove } from "./carousel";
import { checkMessage } from "./messages";

const mocks = vi.hoisted(() => ({ patch: vi.fn(), upload: vi.fn() }));
vi.mock("./hooks", () => ({
  usePatchContent: () => ({ mutateAsync: mocks.patch, isPending: false, error: null }),
  useUploadMedia: () => ({ mutateAsync: mocks.upload, isPending: false, error: null }),
  useMediaPreview: () => ({ url: null, isPending: false, error: null }),
}));
vi.mock("@/features/inbox/hooks", () => ({ useSocialAccounts: () => ({ data: [], isSuccess: true }) }));

const media = (ids: string[]) => ids.map((id, position) => ({ media_asset_id: id, position, width: 1080, height: 1350, media_deleted: false }));
const item = (ids = ["a", "b", "c"]) => contentItem({ content_type: "feed_carousel", version: 7, media_items: media(ids) });
const show = (ids?: string[]) => render(<I18nextProvider i18n={i18n}><CarouselMedia item={item(ids)} workspaceId="workspace" /></I18nextProvider>);
beforeEach(() => { mocks.patch.mockReset(); mocks.upload.mockReset(); });

describe("carousel list operations", () => {
  it("moves up/down and leaves boundaries unchanged", () => {
    expect(move(["a", "b", "c"], 1, 0)).toEqual(["b", "a", "c"]);
    expect(move(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]);
    for (const [from, to] of [[0, -1], [2, 3], [0, 0], [-1, 1]]) expect(move(["a", "b", "c"], from!, to!)).toEqual(["a", "b", "c"]);
  });
  it("removes and appends distinct ids up to the cap", () => {
    expect(remove(["a", "b", "c"], 1)).toEqual(["a", "c"]);
    expect(append(["a"], ["b", "b", "c"], 2)).toEqual(["a", "b"]);
  });
});

it.each(["tr", "en"])("renders every carousel check in %s with positions", async (language) => {
  await i18n.changeLanguage(language);
  for (const code of [...CAROUSEL_CODES, "CONTENT_MEDIA_REQUIRED", "ASPECT_RATIO_OUT_OF_RANGE", "MEDIA_NOT_READY"]) {
    const message = checkMessage({ code, params: { positions: [2, 4], count: 11, max: 10, width: 100, height: 100 }, field: "media_asset_ids.2" }, i18n.t);
    expect(message).not.toContain(code);
    expect(message).toContain("3");
    expect(message).not.toMatch(/\{\{/);
    if (code === "CAROUSEL_MIXED_ASPECT_RATIO") expect(message).toContain("2, 4");
  }
});

it("PATCHes button reorder with expectedVersion and disables first/last controls", async () => {
  await i18n.changeLanguage("en");
  mocks.patch.mockResolvedValue(item(["b", "a", "c"]));
  show();
  expect(screen.getByRole("button", { name: "Move image 1 up" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Move image 3 down" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Move image 2 up" }));
  await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith({ expectedVersion: 7, changes: { media_asset_ids: ["b", "a", "c"] } }));
  await screen.findByText("Image 2 moved to position 1.");
});

it("does not PATCH unchanged or out-of-bounds order", async () => {
  await i18n.changeLanguage("en");
  show();
  fireEvent.click(screen.getByRole("button", { name: "Move image 1 up" }));
  const row = screen.getAllByRole("listitem")[0]!;
  fireEvent.dragStart(row); fireEvent.drop(row);
  expect(mocks.patch).not.toHaveBeenCalled();
});

it("moves down using the same versioned PATCH path", async () => {
  await i18n.changeLanguage("en");
  mocks.patch.mockResolvedValue(item(["a", "c", "b"]));
  show();
  fireEvent.click(screen.getByRole("button", { name: "Move image 2 down" }));
  await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith({ expectedVersion: 7, changes: { media_asset_ids: ["a", "c", "b"] } }));
});

it.each(["tr", "en"])("starts a blank carousel and disables AI/templates in %s", async (language) => {
  await i18n.changeLanguage(language);
  const start = vi.fn();
  render(<I18nextProvider i18n={i18n}><CurrentWorkspaceContext.Provider value={{ workspace: workspace(WS_GOLKENT), role: "owner" }}><ContentComposer onStart={start} onTemplate={vi.fn()} /></CurrentWorkspaceContext.Provider></I18nextProvider>);
  fireEvent.click(screen.getByRole("radio", { name: language === "tr" ? "Kaydırmalı" : "Carousel" }));
  expect(screen.getByRole("button", { name: i18n.t("content.actions.newDraft") })).toBeDisabled();
  expect(screen.queryByRole("button", { name: i18n.t("content.actions.newFromTemplate") })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("content.actions.blankDraft") }));
  expect(start).toHaveBeenCalledWith("blank", "feed_carousel");
});

it("uploads sequentially, appends in order and never uploads past 10", async () => {
  await i18n.changeLanguage("en");
  const ids = Array.from({ length: 8 }, (_, i) => `existing-${i}`);
  let calls = 0;
  mocks.upload.mockImplementation(async () => mediaAsset({ id: `new-${++calls}` }));
  mocks.patch.mockImplementation(async ({ expectedVersion, changes }) => ({ ...item(changes.media_asset_ids), version: expectedVersion + 1 }));
  show(ids);
  fireEvent.change(screen.getByLabelText("Add images"), { target: { files: ["1.jpg", "2.png", "3.jpg"].map((name) => new File(["image"], name, { type: "image/jpeg" })) } });
  await waitFor(() => expect(mocks.patch).toHaveBeenCalledTimes(2));
  expect(mocks.upload).toHaveBeenCalledTimes(2);
  expect(mocks.patch.mock.calls[0]?.[0]).toEqual({ expectedVersion: 7, changes: { media_asset_ids: [...ids, "new-1"] } });
  expect(mocks.patch.mock.calls[1]?.[0]).toEqual({ expectedVersion: 8, changes: { media_asset_ids: [...ids, "new-1", "new-2"] } });
  expect(screen.getByText("Maximum 10 images. Extra files were not uploaded.")).toBeInTheDocument();
});
