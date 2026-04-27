from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from ..service import AccountService
from .deps import get_account_service, require_customer
from .dto import (
    AccountResponse,
    BalanceResponse,
    CreateCheckingAccountRequest,
    CreateSavingsAccountRequest,
    CreateTimeDepositAccountRequest,
    MoneyOperationRequest,
    TransactionResponse,
    TransferRequest,
)

router = APIRouter(prefix="/api", tags=["account"], dependencies=[Depends(require_customer)])


@router.post("/accounts/checking", status_code=201, response_model=AccountResponse)
async def create_checking(
    owner_id: UUID,
    body: CreateCheckingAccountRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    a = await service.create_checking(owner_id, body.currency, body.overdraft_limit)
    return AccountResponse.from_entity(a)


@router.post("/accounts/savings", status_code=201, response_model=AccountResponse)
async def create_savings(
    owner_id: UUID,
    body: CreateSavingsAccountRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    a = await service.create_savings(owner_id, body.currency, body.annual_interest_rate)
    return AccountResponse.from_entity(a)


@router.post("/accounts/time-deposit", status_code=201, response_model=AccountResponse)
async def create_time_deposit(
    owner_id: UUID,
    body: CreateTimeDepositAccountRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    a = await service.create_time_deposit(
        owner_id, body.currency, body.principal, body.maturity_date, body.annual_interest_rate
    )
    return AccountResponse.from_entity(a)


@router.get("/customers/{customer_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    customer_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    accounts = await service.list_accounts(customer_id)
    return [AccountResponse.from_entity(a) for a in accounts]


@router.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
async def get_balance(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    amount, currency = await service.get_balance(account_id)
    return BalanceResponse(amount=amount, currency=currency.value)


@router.post("/accounts/{account_id}/deposit", status_code=201, response_model=TransactionResponse)
async def deposit(
    account_id: UUID,
    body: MoneyOperationRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    t = await service.deposit(account_id, body.amount, body.currency)
    return TransactionResponse.from_entity(t)


@router.post("/accounts/{account_id}/withdraw", status_code=201, response_model=TransactionResponse)
async def withdraw(
    account_id: UUID,
    body: MoneyOperationRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    t = await service.withdraw(account_id, body.amount, body.currency)
    return TransactionResponse.from_entity(t)


@router.post("/accounts/{account_id}/transfer", status_code=200)
async def transfer(
    account_id: UUID,
    body: TransferRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    await service.transfer(account_id, body.target_account_id, body.amount, body.currency)
    return {"status": "ok"}


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionResponse])
async def get_transactions(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
):
    txs = await service.get_transactions(account_id)
    return [TransactionResponse.from_entity(t) for t in txs]
