"""RFC 9457 ``application/problem+json`` responses (api-design.md §1)."""

from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.core.i18n import normalize_locale, t
from app.core.logging import get_logger

PROBLEM_JSON = "application/problem+json"
_log = get_logger(__name__)

_STATUS_TO_CODE = {
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT_STATE",
    422: "VALIDATION_FAILED",
}

# Pydantic error types -> stable machine codes for ``errors[].code``.
_VALIDATION_CODES = {
    "missing": "required",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "string_pattern_mismatch": "invalid_format",
    "value_error": "invalid",
    "literal_error": "invalid_choice",
    "enum": "invalid_choice",
    "uuid_parsing": "invalid_uuid",
    "uuid_type": "invalid_uuid",
    "json_invalid": "invalid_json",
}


def request_id_of(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def request_locale(request: Request) -> str:
    header = request.headers.get("accept-language", "")
    first = header.split(",")[0].split(";")[0] if header else None
    return normalize_locale(first)


def problem_response(
    request: Request,
    *,
    code: str,
    status: int,
    params: dict[str, Any] | None = None,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_of(request)
    locale = request_locale(request)
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else "Error",
        "status": status,
        "code": code,
        "params": params or {},
        "detail": t(f"errors.{code}.what", locale, request_id=request_id or "-"),
        "request_id": request_id,
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def _json_safe(ctx: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in ctx.items() if isinstance(v, str | int | float | bool)}


def _validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for err in exc.errors():
        location = [str(part) for part in err["loc"] if part not in ("body", "query", "path")]
        out.append(
            {
                "field": ".".join(location),
                "code": _VALIDATION_CODES.get(str(err["type"]), "invalid"),
                "params": _json_safe(err.get("ctx") or {}),
            }
        )
    return out


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    params = dict(error.params)
    # Services raise VALIDATION_FAILED (and, for a submission, CONTENT_VALIDATION_FAILED) with
    # ``errors=[{field, code, params}]``, which belongs at the top level of the problem document
    # (api-design.md §1), not inside ``params``.
    errors = (
        params.pop("errors", None)
        if error.code in ("VALIDATION_FAILED", "CONTENT_VALIDATION_FAILED")
        else None
    )
    return problem_response(
        request, code=error.code, status=error.http_status or 500, params=params, errors=errors
    )


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    return problem_response(
        request, code="VALIDATION_FAILED", status=422, errors=_validation_errors(error)
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    code = _STATUS_TO_CODE.get(error.status_code)
    if code is None:
        code = "INTERNAL_ERROR" if error.status_code >= 500 else "VALIDATION_FAILED"
    headers = dict(error.headers) if error.headers else None
    return problem_response(request, code=code, status=error.status_code, headers=headers)


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.error("unhandled_exception", exc_info=exc, path=request.url.path)
    return problem_response(request, code="INTERNAL_ERROR", status=500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
