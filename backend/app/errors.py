from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


STATUS_TO_CODE = {
    400: 'BAD_REQUEST',
    401: 'UNAUTHORIZED',
    403: 'FORBIDDEN',
    404: 'NOT_FOUND',
    409: 'CONFLICT',
    422: 'VALIDATION_ERROR',
    429: 'RATE_LIMITED',
    500: 'INTERNAL_ERROR',
    502: 'UPSTREAM_ERROR',
    503: 'SERVICE_UNAVAILABLE',
}


def _error_body(code: str, message: str, details: dict | list | None = None) -> dict:
    return {
        'error': {
            'code': code,
            'message': message,
            'details': details or {},
        }
    }


def install_exception_handlers(app) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_body('VALIDATION_ERROR', 'Request validation failed', {'errors': exc.errors()}),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        code = STATUS_TO_CODE.get(exc.status_code, 'HTTP_ERROR')

        if isinstance(exc.detail, dict):
            provided_code = exc.detail.get('code')
            message = exc.detail.get('message', 'Request failed')
            details = exc.detail.get('details', {})
            return JSONResponse(
                status_code=exc.status_code,
                content=_error_body(provided_code or code, message, details),
            )

        message = str(exc.detail) if exc.detail else 'Request failed'
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(_request: Request, exc: StarletteHTTPException):
        code = STATUS_TO_CODE.get(exc.status_code, 'HTTP_ERROR')
        message = str(exc.detail) if exc.detail else 'Request failed'
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, _exc: Exception):
        return JSONResponse(
            status_code=500,
            content=_error_body('INTERNAL_ERROR', 'Unexpected server error'),
        )
