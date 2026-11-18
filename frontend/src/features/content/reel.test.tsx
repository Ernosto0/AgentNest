import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n, { setLanguage } from "@/i18n";
import { contentItem } from "@/test/contentFixtures";
import { WS_GOLKENT, workspace } from "@/test/fixtures";
import { CurrentWorkspaceContext } from "@/features/workspaces/context";
import { ContentComposer } from "./ContentComposer";
import { ContentStatusPanel } from "./ContentStatusPanel";
import { FailureDetail } from "./FailureDetail";
import { ReelMedia } from "./ReelMedia";
import {
  REEL_CODES,
  REEL_COVER_MAX_BYTES,
  VIDEO_MAX_BYTES,
  formatVideoTime,
  isAcceptedCoverFile,
  isAcceptedVideoFile,
  reelMessage,
  validateCoverFile,
  validateVideoFile,
} from "./reel";

const VIDEO_ID = "11111111-1111-4111-8111-111111111111";
const COVER_ID = "22222222-2222-4222-8222-222222222222";

function renderReel(
  overrides: Partial<ReturnType<typeof contentItem>> = {},
  fetchMock?: typeof fetch,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const item = contentItem({
    content_type: "reel",
    version: 3,
    media_asset_id: VIDEO_ID,
    video_duration_ms: 12_500,
    share_to_feed: true,
    ...overrides,
  });
  const ws = workspace(WS_GOLKENT);
  if (fetchMock) {
    vi.stubGlobal("fetch", fetchMock);
  }
  const view = render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CurrentWorkspaceContext.Provider value={{ workspace: ws, role: "owner" }}>
            <ReelMedia item={item} workspaceId={ws.id} />
          </CurrentWorkspaceContext.Provider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
  return { ...view, item, ws };
}

class FakeXhr {
  static instances: FakeXhr[] = [];
  method = "";
  url = "";
  withCredentials = false;
  headers: Record<string, string> = {};
  status = 200;
  responseText = "";
  aborted = false;
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXhr.instances.push(this);
  }
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  send() {}
  abort() {
    this.aborted = true;
    this.onabort?.();
  }
  emitProgress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total } as ProgressEvent);
  }
  emitSuccess(body: unknown, status = 201) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}

afterEach(async () => {
  FakeXhr.instances = [];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  await setLanguage("tr");
});

describe("reel pure helpers", () => {
  it("validates video & JPEG cover files and formats timestamps", () => {
    expect(isAcceptedVideoFile({ name: "clip.mp4", type: "video/mp4" })).toBe(true);
    expect(isAcceptedVideoFile({ name: "clip.MOV", type: "video/quicktime" })).toBe(true);
    expect(isAcceptedVideoFile({ name: "clip.mp4", type: "" })).toBe(true);
    expect(isAcceptedVideoFile({ name: "photo.jpg", type: "image/jpeg" })).toBe(false);

    expect(validateVideoFile({ name: "a.mp4", type: "video/mp4", size: 100 })).toBeNull();
    expect(validateVideoFile({ name: "a.png", type: "image/png", size: 100 })).toBe("type");
    expect(validateVideoFile({ name: "big.mp4", type: "video/mp4", size: VIDEO_MAX_BYTES + 1 })).toBe("size");

    expect(isAcceptedCoverFile({ name: "c.jpg", type: "image/jpeg" })).toBe(true);
    expect(isAcceptedCoverFile({ name: "c.png", type: "image/png" })).toBe(false);
    expect(validateCoverFile({ name: "c.jpg", type: "image/jpeg", size: REEL_COVER_MAX_BYTES })).toBeNull();
    expect(validateCoverFile({ name: "c.jpg", type: "image/jpeg", size: REEL_COVER_MAX_BYTES + 1 })).toBe("size");

    expect(formatVideoTime(0)).toBe("0:00");
    expect(formatVideoTime(7300, true)).toBe("0:07.3");
    expect(formatVideoTime(95_000)).toBe("1:35");
  });

  it.each(["tr", "en"] as const)("translates every reel check code in %s", async (lang) => {
    await setLanguage(lang);
    for (const code of REEL_CODES) {
      const msg = reelMessage(code, {}, i18n.t.bind(i18n));
      expect(msg).not.toBeNull();
      expect(msg).not.toContain("content.editor.checks.");
    }
  });
});

describe("ReelMedia upload, scrub, cover & disclosure", () => {
  it("tracks XHR video upload progress, probing state, cancel, and client rejection", async () => {
    await setLanguage("tr");
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const parseFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = req ? req.url : String(input);
      const method = (init?.method ?? req?.method ?? "GET").toUpperCase();
      const bodyText = req ? await req.clone().text() : init?.body ? String(init.body) : "";
      return { url, method, bodyText };
    };
    const patchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const { url, method } = await parseFetch(input, init);
      if (url.endsWith(`/content-items/${contentItem().id}`) && method === "PATCH") {
        return new Response(JSON.stringify(contentItem({ content_type: "reel", version: 4, media_asset_id: VIDEO_ID })), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ id: VIDEO_ID, kind: "video", mime_type: "video/mp4", byte_size: 100, width: 1080, height: 1920, duration_ms: 12_500, video_warnings: [], status: "ready" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    renderReel({ media_asset_id: null, video_duration_ms: null }, patchMock);

    const fileInput = document.querySelector('input[type="file"][accept*="video/mp4"]') as HTMLInputElement;
    // Wrong file type rejected before opening XHR
    fireEvent.change(fileInput, { target: { files: [new File(["x"], "bad.png", { type: "image/png" })] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("MP4 veya MOV");
    expect(FakeXhr.instances).toHaveLength(0);

    // Valid video opens XHR, shows progress and probing, then patches item
    fireEvent.change(fileInput, { target: { files: [new File(["video"], "clip.mp4", { type: "video/mp4" })] } });
    expect(FakeXhr.instances).toHaveLength(1);
    const xhr = FakeXhr.instances[0]!;
    expect(xhr.method).toBe("POST");
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.url).toContain("/media/video");

    act(() => {
      xhr.emitProgress(50_000_000, 100_000_000);
    });
    await waitFor(() => expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50"));
    expect(screen.getByText(/50\.0 MB \/ 100\.0 MB/)).toBeInTheDocument();
    act(() => {
      xhr.emitProgress(100_000_000, 100_000_000);
    });
    await waitFor(() => expect(screen.getAllByText("Dosya işleniyor…").length).toBeGreaterThan(0));

    act(() => {
      xhr.emitSuccess({ id: VIDEO_ID, kind: "video", mime_type: "video/mp4", byte_size: 100, width: 1080, height: 1920, duration_ms: 12_500, video_warnings: [], status: "ready" });
    });
    await waitFor(() => expect(patchMock).toHaveBeenCalled());

    // Cancel aborts without patching
    fireEvent.change(fileInput, { target: { files: [new File(["video"], "clip2.mp4", { type: "video/mp4" })] } });
    expect(FakeXhr.instances).toHaveLength(2);
    const xhr2 = FakeXhr.instances[1]!;
    fireEvent.click(screen.getByRole("button", { name: "İptal" }));
    expect(xhr2.aborted).toBe(true);
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("seeks video element on range change, saves thumb_offset_ms, uploads cover, resets, toggles share_to_feed, and shows disclosure", async () => {
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => {});
    let setCurrentTime: number | undefined;
    Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
      configurable: true,
      get: () => setCurrentTime ?? 0,
      set: (val: number) => {
        setCurrentTime = val;
      },
    });

    const patches: Record<string, unknown>[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = req ? req.url : String(input);
      const method = (init?.method ?? req?.method ?? "GET").toUpperCase();
      if (method === "PATCH") {
        const raw = req ? await req.clone().text() : String(init?.body ?? "{}");
        const body = JSON.parse(raw) as Record<string, unknown>;
        patches.push(body);
        return new Response(
          JSON.stringify(
            contentItem({
              content_type: "reel",
              version: 4,
              media_asset_id: VIDEO_ID,
              video_duration_ms: 12_500,
              cover_media_asset_id: (body.cover_media_asset_id as string | null | undefined) ?? null,
              thumb_offset_ms: (body.thumb_offset_ms as number | null | undefined) ?? null,
              share_to_feed: (body.share_to_feed as boolean | undefined) ?? true,
            }),
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/media") && method === "POST") {
        return new Response(JSON.stringify({ id: COVER_ID, kind: "image", mime_type: "image/jpeg", byte_size: 1200, width: 1080, height: 1920, status: "ready" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith(`/media/${VIDEO_ID}`)) {
        return new Response(JSON.stringify({ id: VIDEO_ID, kind: "video", mime_type: "video/mp4", byte_size: 100, width: 720, height: 1280, duration_ms: 12_500, video_warnings: ["ASPECT_NOT_9_16"], status: "ready" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(new Blob(["img"]), { status: 200 });
    });

    renderReel({ cover_media_asset_id: COVER_ID }, fetchMock);
    expect(screen.getByRole("note")).toHaveTextContent("otomatik olarak bilgi kontrolünden geçmez");
    await waitFor(() => expect(screen.getByText(/Video 9:16 oranında değil/)).toBeInTheDocument());

    const slider = screen.getByRole("slider");
    expect(slider).toHaveAttribute("max", "12400");
    fireEvent.change(slider, { target: { value: "4200" } });
    expect(slider).toHaveAttribute("aria-valuetext", "0:04.2");
    expect(setCurrentTime).toBe(4.2);

    fireEvent.click(screen.getByRole("button", { name: "Bu kareyi kullan" }));
    await waitFor(() => expect(patches.some((p) => p.thumb_offset_ms === 4200 && p.cover_media_asset_id === null)).toBe(true));

    fireEvent.click(screen.getByRole("button", { name: "İlk kareyi kullan" }));
    await waitFor(() => expect(patches.some((p) => p.thumb_offset_ms === null && p.cover_media_asset_id === null)).toBe(true));

    const coverInput = document.querySelector('input[type="file"][accept*="image/jpeg"]') as HTMLInputElement;
    fireEvent.change(coverInput, { target: { files: [new File(["jpg"], "cover.jpg", { type: "image/jpeg" })] } });
    await waitFor(() => expect(patches.some((p) => p.cover_media_asset_id === COVER_ID && p.thumb_offset_ms === null)).toBe(true));

    const toggle = screen.getByRole("switch");
    fireEvent.click(toggle);
    await waitFor(() => expect(patches.some((p) => p.share_to_feed === false)).toBe(true));
  });

  it("does not send a PATCH when thumb_offset_ms is unchanged", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      async () => new Response(new Blob(["img"]), { status: 200 }),
    );
    renderReel({ cover_media_asset_id: null, thumb_offset_ms: 3500 }, fetchMock);
    const slider = screen.getByRole("slider");
    expect(slider).toHaveAttribute("aria-valuetext", "0:03.5");
    fireEvent.click(screen.getByRole("button", { name: "Bu kareyi kullan" }));
    const patchCalls = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patchCalls).toHaveLength(0);
  });
});

describe("reel composer, processing panel & timeout failure", () => {
  it.each(["tr", "en"] as const)("disables AI/templates for reel in %s composer", async (lang) => {
    await setLanguage(lang);
    const start = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <CurrentWorkspaceContext.Provider value={{ workspace: workspace(WS_GOLKENT), role: "owner" }}>
              <ContentComposer onStart={start} onTemplate={() => {}} />
            </CurrentWorkspaceContext.Provider>
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("radio", { name: lang === "tr" ? "Reels" : "Reel" }));
    expect(screen.getByRole("button", { name: i18n.t("content.actions.newDraft") })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: i18n.t("content.actions.blankDraft") }));
    expect(start).toHaveBeenCalledWith("blank", "reel");
  });

  it("renders processing status panel with next check time and REEL_PROCESSING_TIMEOUT failure detail", async () => {
    await setLanguage("tr");
    const ws = workspace(WS_GOLKENT);
    const processingItem = contentItem({
      content_type: "reel",
      status: "publishing",
      operation: {
        status: "in_progress",
        attempts: 1,
        next_attempt_at: "2026-04-20T16:15:00Z",
        last_error_code: null,
        processing: true,
      },
    });
    render(
      <I18nextProvider i18n={i18n}>
        <CurrentWorkspaceContext.Provider value={{ workspace: ws, role: "owner" }}>
          <ContentStatusPanel item={processingItem} />
          <FailureDetail
            item={contentItem({ content_type: "reel", status: "failed", last_error_code: "REEL_PROCESSING_TIMEOUT" })}
            onEdit={() => {}}
          />
        </CurrentWorkspaceContext.Provider>
      </I18nextProvider>,
    );
    expect(screen.getByText(/Instagram bu reels videosunu işliyor/)).toBeInTheDocument();
    expect(screen.getByText(/Sonraki durum kontrolü:/)).toBeInTheDocument();
    expect(screen.getByText(/zaman aşımına uğradı/)).toBeInTheDocument();
  });
});
