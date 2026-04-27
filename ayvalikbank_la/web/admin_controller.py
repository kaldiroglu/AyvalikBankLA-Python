from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from ..service import AccountService, CustomerService
from .deps import get_account_service, get_customer_service, require_admin
from .dto import (
    AccrueInterestRequest,
    ChangeCustomerTierRequest,
    CreateCustomerRequest,
    CustomerResponse,
    SetTransferFeeRequest,
    TransactionResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/customers", status_code=201, response_model=CustomerResponse)
async def create_customer(
    body: CreateCustomerRequest,
    service: Annotated[CustomerService, Depends(get_customer_service)],
):
    c = await service.create_customer(body.name, body.email, body.password)
    return CustomerResponse.from_entity(c)


@router.delete("/customers/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: UUID,
    service: Annotated[CustomerService, Depends(get_customer_service)],
):
    await service.delete_customer(customer_id)


@router.get("/customers", response_model=list[CustomerResponse])
async def list_customers(
    service: Annotated[CustomerService, Depends(get_customer_service)],
):
    return [CustomerResponse.from_entity(c) for c in await service.list_customers()]


@router.put("/customers/{customer_id}/tier", status_code=200)
async def change_tier(
    customer_id: UUID,
    body: ChangeCustomerTierRequest,
    service: Annotated[CustomerService, Depends(get_customer_service)],
):
    await service.change_customer_tier(customer_id, body.tier)
    return {"status": "ok"}


@router.put("/settings/transfer-fee", status_code=200)
async def set_transfer_fee(
    body: SetTransferFeeRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    await service.set_transfer_fee_percent(body.fee_percent)
    return {"status": "ok"}


@router.put("/accounts/{account_id}/freeze", status_code=200)
async def freeze(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    await service.freeze_account(account_id)
    return {"status": "ok"}


@router.put("/accounts/{account_id}/unfreeze", status_code=200)
async def unfreeze(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    await service.unfreeze_account(account_id)
    return {"status": "ok"}


@router.put("/accounts/{account_id}/close", status_code=200)
async def close(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    await service.close_account(account_id)
    return {"status": "ok"}


@router.put("/accounts/{account_id}/accrue-interest", status_code=200, response_model=TransactionResponse)
async def accrue_interest(
    account_id: UUID,
    body: AccrueInterestRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    t = await service.accrue_interest(account_id, body.year, body.month)
    return TransactionResponse.from_entity(t)


@router.put("/accounts/{account_id}/mature", status_code=200, response_model=TransactionResponse)
async def mature(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    t = await service.mature_time_deposit(account_id)
    return TransactionResponse.from_entity(t)
