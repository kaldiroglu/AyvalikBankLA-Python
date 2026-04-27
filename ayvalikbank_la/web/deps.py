from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ..service import AccountService, CustomerService


async def get_customer_service() -> CustomerService:  # pragma: no cover
    raise NotImplementedError("Override in composition root")


async def get_account_service() -> AccountService:  # pragma: no cover
    raise NotImplementedError("Override in composition root")


_basic = HTTPBasic(auto_error=False)


async def authenticate(
    creds: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
):
    if creds is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Basic"})
    from sqlalchemy import select

    from ..model import Customer

    session = customer_service._session  # type: ignore[attr-defined]
    hasher = customer_service._hasher  # type: ignore[attr-defined]
    result = await session.execute(select(Customer).where(Customer.email == creds.username))
    customer = result.scalar_one_or_none()
    if customer is None or not hasher.matches(creds.password, customer.current_password_hash):
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return customer


def require_role(*roles: str):
    async def _dep(customer=Depends(authenticate)):
        if customer.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return customer

    return _dep


require_admin = require_role("ADMIN")
require_customer = require_role("CUSTOMER", "ADMIN")
