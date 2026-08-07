"""Orchestration coverage that test_account_service.py did not have.

Repository lookups, status transitions, transfer fees and not-found handling. Ported from
AyvalikBankLA-JAVA's AccountServiceTest.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from ayvalikbank_la.exception import (
    AccountNotOperableException,
    InsufficientFundsException,
    LimitExceededException,
    NotFoundException,
)
from ayvalikbank_la.model import AccountStatus, Currency, Customer
from ayvalikbank_la.service import AccountService, TransferService


async def _add_customer(session, tier: str = "STANDARD") -> UUID:
    c = Customer(
        id=uuid4(), name="alice", email=f"alice-{uuid4()}@example.com",
        role="CUSTOMER", tier=tier, current_password_hash="x",
    )
    session.add(c)
    await session.flush()
    return c.id


@pytest.fixture
def svc(session) -> AccountService:
    return AccountService(session, TransferService())


async def _funded(svc, session, amount: str = "0", tier: str = "STANDARD"):
    owner = await _add_customer(session, tier)
    a = await svc.create_checking(owner, Currency.USD, Decimal("0"))
    if Decimal(amount) > 0:
        await svc.deposit(owner, a.id, Decimal(amount), Currency.USD)
    return owner, a


@pytest.mark.asyncio
async def test_creating_an_account_for_a_missing_customer_is_not_found(svc):
    with pytest.raises(NotFoundException):
        await svc.create_checking(uuid4(), Currency.USD, Decimal("0"))


@pytest.mark.asyncio
async def test_deposit_credits_the_account(svc, session):
    owner, a = await _funded(svc, session)

    await svc.deposit(owner, a.id, Decimal("200"), Currency.USD)

    amount, _ = await svc.get_balance(owner, a.id)
    assert amount == Decimal("200")


@pytest.mark.asyncio
async def test_deposit_into_a_missing_account_is_not_found(svc):
    with pytest.raises(NotFoundException):
        await svc.deposit(uuid4(), uuid4(), Decimal("10"), Currency.USD)


@pytest.mark.asyncio
async def test_withdrawal_beyond_the_balance_is_rejected(svc, session):
    owner, a = await _funded(svc, session, "100")

    with pytest.raises(InsufficientFundsException):
        await svc.withdraw(owner, a.id, Decimal("500"), Currency.USD)


@pytest.mark.asyncio
async def test_transfer_between_one_customers_own_accounts_is_free(svc, session):
    owner, src = await _funded(svc, session, "500")
    tgt = await svc.create_checking(owner, Currency.USD, Decimal("0"))

    await svc.transfer(owner, src.id, tgt.id, Decimal("200"), Currency.USD)

    src_amount, _ = await svc.get_balance(owner, src.id)
    tgt_amount, _ = await svc.get_balance(owner, tgt.id)
    assert src_amount == Decimal("300")
    assert tgt_amount == Decimal("200")


@pytest.mark.asyncio
async def test_transfer_between_different_customers_deducts_the_fee(svc, session):
    sender, src = await _funded(svc, session, "1000")
    recipient = await _add_customer(session)
    tgt = await svc.create_checking(recipient, Currency.USD, Decimal("0"))
    await svc.set_transfer_fee_percent(Decimal("1.0"))

    await svc.transfer(sender, src.id, tgt.id, Decimal("200"), Currency.USD)

    src_amount, _ = await svc.get_balance(sender, src.id)
    tgt_amount, _ = await svc.get_balance(recipient, tgt.id)
    assert src_amount == Decimal("798")
    assert tgt_amount == Decimal("200")


@pytest.mark.asyncio
async def test_transfer_above_the_standard_cap_is_rejected(svc, session):
    sender, src = await _funded(svc, session, "10000")
    recipient = await _add_customer(session)
    tgt = await svc.create_checking(recipient, Currency.USD, Decimal("0"))

    with pytest.raises(LimitExceededException):
        await svc.transfer(sender, src.id, tgt.id, Decimal("5001"), Currency.USD)


@pytest.mark.asyncio
async def test_freezes_then_unfreezes(svc, session):
    owner, a = await _funded(svc, session, "100")

    await svc.freeze_account(a.id)
    assert (await svc._require_account(a.id)).status == AccountStatus.FROZEN.value

    await svc.unfreeze_account(a.id)
    assert (await svc._require_account(a.id)).status == AccountStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_closes_an_account(svc, session):
    owner, a = await _funded(svc, session)

    await svc.close_account(a.id)

    assert (await svc._require_account(a.id)).status == AccountStatus.CLOSED.value


@pytest.mark.asyncio
async def test_freezing_a_closed_account_is_not_operable(svc, session):
    owner, a = await _funded(svc, session)
    await svc.close_account(a.id)

    with pytest.raises(AccountNotOperableException):
        await svc.freeze_account(a.id)


@pytest.mark.asyncio
async def test_freezing_a_missing_account_is_not_found(svc):
    with pytest.raises(NotFoundException):
        await svc.freeze_account(uuid4())


@pytest.mark.asyncio
async def test_maturing_a_non_time_deposit_is_rejected(svc, session):
    owner, a = await _funded(svc, session)

    with pytest.raises(AccountNotOperableException):
        await svc.mature_time_deposit(a.id)


@pytest.mark.asyncio
async def test_withdrawal_from_an_unmatured_time_deposit_is_rejected(svc, session):
    owner = await _add_customer(session)
    td = await svc.create_time_deposit(
        owner, Currency.USD, Decimal("1000"), date.today() + timedelta(days=365), Decimal("0.05")
    )

    with pytest.raises(AccountNotOperableException):
        await svc.withdraw(owner, td.id, Decimal("100"), Currency.USD)
