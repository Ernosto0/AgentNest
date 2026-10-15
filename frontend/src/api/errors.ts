import type { TFunction } from "i18next";

export interface FieldError {
  field: string;
  code: string;
  params: Record<string, unknown>;
}

/** An RFC 9457 problem document from the API, or a network failure (`status` 0). */
export class AppError extends Error {
  readonly code: string;
  readonly status: number;
  readonly params: Record<string, unknown>;
  readonly requestId: string | null;
  readonly fieldErrors: FieldError[];

  constructor(
    code: string,
    status: number,
    options: {
      params?: Record<string, unknown>;
      requestId?: string | null;
      fieldErrors?: FieldError[];
    } = {},
  ) {
    super(code);
    this.name = "AppError";
    this.code = code;
    this.status = status;
    this.params = options.params ?? {};
    this.requestId = options.requestId ?? null;
    this.fieldErrors = options.fieldErrors ?? [];
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Turn a problem+json body into an `AppError`; tolerant of bodies that are not problems. */
export function parseProblem(status: number, body: unknown): AppError {
  if (!isRecord(body) || typeof body.code !== "string") {
    return new AppError(status >= 500 ? "INTERNAL_ERROR" : "UNKNOWN", status);
  }
  const fieldErrors = Array.isArray(body.errors)
    ? body.errors.filter(isRecord).map((e) => ({
        field: String(e.field ?? ""),
        code: String(e.code ?? "invalid"),
        params: isRecord(e.params) ? e.params : {},
      }))
    : [];
  return new AppError(body.code, status, {
    params: isRecord(body.params) ? body.params : {},
    requestId: typeof body.request_id === "string" ? body.request_id : null,
    fieldErrors,
  });
}

export interface LocalizedError {
  what: string;
  next: string;
  requestId: string | null;
}

/** Plain-language message for any thrown value, from the error code (never raw exception text). */
export function localizeError(error: unknown, t: TFunction): LocalizedError {
  const code = error instanceof AppError ? error.code : "UNKNOWN";
  const known = `errors.${code}.what`;
  const key = t(known, { defaultValue: "" }) ? code : "UNKNOWN";
  return {
    what: t(`errors.${key}.what`),
    next: t(`errors.${key}.next`),
    requestId: error instanceof AppError ? error.requestId : null,
  };
}
