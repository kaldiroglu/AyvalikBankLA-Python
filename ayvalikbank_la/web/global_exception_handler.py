from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..exception import (
    AccountNotOperableException,
    InsufficientFundsException,
    InvalidAccountOperationException,
    InvalidCredentialsException,
    LimitExceededException,
    NotFoundException,
    PasswordReuseException,
    PasswordValidationException,
    UnauthorizedAccessException,
)


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundException)
    async def _nf(req: Request, exc: NotFoundException):
        return _problem(404, "Not Found", str(exc))

    @app.exception_handler(UnauthorizedAccessException)
    async def _forbidden(req: Request, exc: UnauthorizedAccessException) -> JSONResponse:
        return _problem(403, "Forbidden", str(exc))

    @app.exception_handler(InvalidCredentialsException)
    async def _ic(req: Request, exc: InvalidCredentialsException):
        return _problem(401, "Invalid Credentials", str(exc))

    @app.exception_handler(PasswordValidationException)
    async def _pv(req: Request, exc: PasswordValidationException):
        return _problem(422, "Password Validation Failed", str(exc))

    @app.exception_handler(PasswordReuseException)
    async def _pr(req: Request, exc: PasswordReuseException):
        return _problem(422, "Password Reused", str(exc))

    @app.exception_handler(InsufficientFundsException)
    async def _if(req: Request, exc: InsufficientFundsException):
        return _problem(422, "Insufficient Funds", str(exc))

    @app.exception_handler(AccountNotOperableException)
    async def _no(req: Request, exc: AccountNotOperableException):
        return _problem(422, "Account Not Operable", str(exc))

    @app.exception_handler(InvalidAccountOperationException)
    async def _io(req: Request, exc: InvalidAccountOperationException):
        return _problem(422, "Invalid Account Operation", str(exc))

    @app.exception_handler(LimitExceededException)
    async def _le(req: Request, exc: LimitExceededException):
        return _problem(422, "Limit Exceeded", str(exc))
