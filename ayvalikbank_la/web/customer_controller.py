from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from ..service import CustomerService
from .deps import get_customer_service, require_customer
from .dto import ChangePasswordRequest

router = APIRouter(prefix="/api/customers", tags=["customer"])


@router.put("/{customer_id}/password", status_code=200)
async def change_password(
    customer_id: UUID,
    body: ChangePasswordRequest,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    _=Depends(require_customer),
):
    await service.change_password(customer_id, body.new_password)
    return {"status": "ok"}
