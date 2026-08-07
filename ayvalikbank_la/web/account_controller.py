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

router = APIRouter(prefix="/api", tags=["account"])


@router.post("/accounts/checking", status_code=201, response_model=AccountResponse)
async def create_checking(
    body: CreateCheckingAccountRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    a = await service.create_checking(caller.id, body.currency, body.overdraft_limit)
    return AccountResponse.from_entity(a)


@router.post("/accounts/savings", status_code=201, response_model=AccountResponse)
async def create_savings(
    body: CreateSavingsAccountRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    a = await service.create_savings(caller.id, body.currency, body.annual_interest_rate)
    return AccountResponse.from_entity(a)


@router.post("/accounts/time-deposit", status_code=201, response_model=AccountResponse)
async def create_time_deposit(
    body: CreateTimeDepositAccountRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    a = await service.create_time_deposit(
        caller.id, body.currency, body.principal, body.maturity_date, body.annual_interest_rate
    )
    return AccountResponse.from_entity(a)


@router.get("/customers/{customer_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    customer_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    accounts = await service.list_accounts(caller.id, customer_id)
    return [AccountResponse.from_entity(a) for a in accounts]


@router.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
async def get_balance(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    amount, currency = await service.get_balance(caller.id, account_id)
    return BalanceResponse(amount=amount, currency=currency.value)


@router.post("/accounts/{account_id}/deposit", status_code=201, response_model=TransactionResponse)
async def deposit(
    account_id: UUID,
    body: MoneyOperationRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    t = await service.deposit(caller.id, account_id, body.amount, body.currency)
    return TransactionResponse.from_entity(t)


@router.post("/accounts/{account_id}/withdraw", status_code=201, response_model=TransactionResponse)
async def withdraw(
    account_id: UUID,
    body: MoneyOperationRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    t = await service.withdraw(caller.id, account_id, body.amount, body.currency)
    return TransactionResponse.from_entity(t)


@router.post("/accounts/{account_id}/transfer", status_code=200)
async def transfer(
    account_id: UUID,
    body: TransferRequest,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    await service.transfer(caller.id, account_id, body.target_account_id, body.amount, body.currency)
    return {"status": "ok"}


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionResponse])
async def get_transactions(
    account_id: UUID,
    service: Annotated[AccountService, Depends(get_account_service)],
    caller=Depends(require_customer),
):
    txs = await service.get_transactions(caller.id, account_id)
    return [TransactionResponse.from_entity(t) for t in txs]
