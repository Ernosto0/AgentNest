import { afterEach, describe, expect, it, vi } from "vitest";
import { json, noContent, problem } from "@/test/mockApi";
import { setLanguage } from "@/i18n";
import { createApiClient, setCsrfToken, unwrap } from "./client";
import { AppError, localizeError, parseProblem } from "./errors";
import i18n from "@/i18n";

afterEach(() => setCsrfToken(null));

function clientWith(respond: () => Response) {
  const calls: Request[] = [];
  const fetchMock = vi.fn(async (request: Request) => {
    calls.push(request);
    return respond();
  });
  return { api: createApiClient({ fetch: fetchMock as unknown as typeof fetch }), calls };
}

describe("api client", () => {
  it("sends the CSRF token on state-changing requests only", async () => {
    setCsrfToken("tok-1");
    const { api, calls } = clientWith(() => noContent());
    await api.POST("/api/v1/auth/logout");
    await api.PATCH("/api/v1/auth/me", { body: { display_name: "A" } });
    const { api: readApi, calls: readCalls } = clientWith(() => json({}));
    await readApi.GET("/api/v1/auth/me");

    expect(calls.map((c) => c.headers.get("x-csrf-token"))).toEqual(["tok-1", "tok-1"]);
    expect(readCalls[0]?.headers.has("x-csrf-token")).toBe(false);
  });

  it("sends no CSRF header when there is no session token", async () => {
    const { api, calls } = clientWith(() => noContent());
    await api.POST("/api/v1/auth/logout");
    expect(calls[0]?.headers.has("x-csrf-token")).toBe(false);
  });

  it("sends cookies and the current UI language", async () => {
    const { api, calls } = clientWith(() => json({}));
    await api.GET("/api/v1/meta");
    expect(calls[0]?.credentials).toBe("include");
    expect(calls[0]?.headers.get("accept-language")).toBe("tr");
    await setLanguage("en");
    await api.GET("/api/v1/meta");
    expect(calls[1]?.headers.get("accept-language")).toBe("en");
  });
});

describe("unwrap", () => {
  it("returns data and tolerates empty 204 bodies", async () => {
    const ok = clientWith(() => json({ product_name: "X" }));
    expect(await unwrap(ok.api.GET("/api/v1/meta"))).toEqual({ product_name: "X" });
    const empty = clientWith(() => noContent());
    expect(await unwrap<void>(empty.api.POST("/api/v1/auth/logout"))).toBeUndefined();
  });

  it("turns a problem+json response into an AppError with code, params and request id", async () => {
    const { api } = clientWith(() =>
      problem(403, "FORBIDDEN", { params: { permission: "workspace.manage" } }),
    );
    const error = await unwrap(api.GET("/api/v1/meta")).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(AppError);
    expect(error).toMatchObject({
      code: "FORBIDDEN",
      status: 403,
      params: { permission: "workspace.manage" },
      requestId: "req-123",
    });
  });

  it("maps validation problems to per-field errors", async () => {
    const { api } = clientWith(() =>
      problem(422, "VALIDATION_FAILED", {
        errors: [{ field: "timezone", code: "invalid_timezone", params: {} }],
      }),
    );
    const error = (await unwrap(api.GET("/api/v1/meta")).catch((e: unknown) => e)) as AppError;
    expect(error.fieldErrors).toEqual([{ field: "timezone", code: "invalid_timezone", params: {} }]);
  });

  it("reports an unreachable server as NETWORK_ERROR instead of leaking exception text", async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError("Failed to fetch: secret internal detail");
    });
    const api = createApiClient({ fetch: fetchMock as unknown as typeof fetch });
    const error = (await unwrap(api.GET("/api/v1/meta")).catch((e: unknown) => e)) as AppError;
    expect(error).toMatchObject({ code: "NETWORK_ERROR", status: 0 });
    expect(error.message).not.toContain("secret");
  });
});

describe("error localisation", () => {
  it("renders the message for a known code in the current language", async () => {
    const error = new AppError("FORBIDDEN", 403, { requestId: "r1" });
    expect(localizeError(error, i18n.t.bind(i18n))).toEqual({
      what: "Rolünüz bu işlem için yetkili değil.",
      next: "Çalışma alanı sahibinden yardım isteyin.",
      requestId: "r1",
    });
    await setLanguage("en");
    expect(localizeError(error, i18n.t.bind(i18n)).what).toBe("Your role cannot do this.");
  });

  it("falls back to a generic message for unknown codes and non-API errors", () => {
    const t = i18n.t.bind(i18n);
    expect(localizeError(new AppError("SOMETHING_NEW", 400), t).what).toBe(
      "Beklenmeyen bir hata oluştu.",
    );
    expect(localizeError(new Error("boom"), t).what).toBe("Beklenmeyen bir hata oluştu.");
    expect(localizeError("string", t).requestId).toBeNull();
  });

  it("copes with bodies that are not problem documents", () => {
    expect(parseProblem(502, "<html>bad gateway</html>")).toMatchObject({ code: "INTERNAL_ERROR" });
    expect(parseProblem(400, undefined)).toMatchObject({ code: "UNKNOWN" });
  });
});
