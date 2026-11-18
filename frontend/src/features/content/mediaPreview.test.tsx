import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { contentItem, mediaAsset } from "@/test/contentFixtures";
import { workspace, WS_GOLKENT } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { CurrentWorkspaceContext } from "@/features/workspaces/context";
import { ContentMedia } from "./ContentMedia";
import { mediaPreviewId } from "./mediaPreview";

afterEach(() => vi.unstubAllGlobals());

it("selects image IDs and video thumbnails, never a video or a bare thumbnail", () => {
  expect(mediaPreviewId(null)).toBeNull();
  expect(mediaPreviewId({ id: "i", kind: "image" })).toBe("i");
  expect(mediaPreviewId({ id: "v", kind: "video", thumbnail_media_asset_id: "t" })).toBe("t");
  expect(mediaPreviewId({ id: "v", kind: "video" })).toBeNull();
  expect(mediaPreviewId({ id: "t", kind: "video_thumbnail" })).toBeNull();
});

it("fetches only the JPEG thumbnail for a video asset in ContentMedia", async () => {
  const base = `/api/v1/workspaces/${WS_GOLKENT}/media`;
  const requests = mockApi({
    [`GET ${base}/video`]: () => json(mediaAsset({ id: "video", kind: "video", thumbnail_media_asset_id: "thumb", duration_ms: 10000 })),
    [`GET ${base}/thumb/content`]: () => new Response(new Blob(["jpeg"], { type: "image/jpeg" }), { headers: { "content-type": "image/jpeg" } }),
  });
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:thumbnail"), revokeObjectURL: vi.fn() }));
  const { container } = render(<I18nextProvider i18n={i18n}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CurrentWorkspaceContext.Provider value={{ workspace: workspace(WS_GOLKENT), role: "owner" }}><ContentMedia item={contentItem({ media_asset_id: "video" })} /></CurrentWorkspaceContext.Provider></QueryClientProvider></I18nextProvider>);
  await waitFor(() => expect(requests.some(r => r.path === `${base}/thumb/content`)).toBe(true));
  expect(requests.some(r => r.path === `${base}/video/content`)).toBe(false);
  await waitFor(() => expect(container.querySelector("img")).toHaveAttribute("src", "blob:thumbnail"));
});
