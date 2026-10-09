from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
