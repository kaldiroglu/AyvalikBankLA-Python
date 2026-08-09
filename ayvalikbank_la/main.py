"""Composition root — wires the FastAPI app for LA-Python."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .config import BcryptHasher, seed_admin
from .repository import Base, get_engine, get_sessionmaker
from .service import AccountService, CustomerService, PasswordValidationService, TransferService
from .web import (
    account_router,
    admin_router,
    customer_router,
    register_exception_handlers,
)
from .web.deps import get_account_service, get_customer_service

DEFAULT_DB_URL = "postgresql+asyncpg://bank:bank@localhost:5435/ayvalikbank_la_python"


def create_app(database_url: str | None = None) -> FastAPI:
    db_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    engine = get_engine(db_url)
    sessionmaker = get_sessionmaker(engine)
    hasher = BcryptHasher()
    validator = PasswordValidationService()
    transfer_service = TransferService()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessionmaker() as session:
            await seed_admin(session, hasher)
        yield
        await engine.dispose()

    app = FastAPI(title="Ayvalık Bank LA-Python", lifespan=lifespan)
    register_exception_handlers(app)

    async def _customer_service():
        async with sessionmaker() as session:
            try:
                yield CustomerService(session, hasher, validator)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _account_service():
        async with sessionmaker() as session:
            try:
                yield AccountService(session, transfer_service)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_customer_service] = _customer_service
    app.dependency_overrides[get_account_service] = _account_service

    app.include_router(customer_router)
    app.include_router(account_router)
    app.include_router(admin_router)
    return app


app = create_app()
