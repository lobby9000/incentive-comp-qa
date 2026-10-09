from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []


def error_body(code: str, message: str, details: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message, exc.details))


async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"loc": [str(p) for p in err.get("loc", [])], "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", "Request is not valid", details))


HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """BUG-007: framework errors (unknown route, wrong method) use the standard envelope."""
    code = HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)),
                        headers=getattr(exc, "headers", None))


async def unhandled_error_handler(request: Request, exc: Exception):
    """BUG-007: unexpected failures still answer with the envelope instead of plain text."""
    return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", "Unexpected server error"))
