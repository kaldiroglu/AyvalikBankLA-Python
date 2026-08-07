"""Service tests against SQLite in-memory — exercise the if/else type dispatch
through real SQLAlchemy save/load cycles."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from ayvalikbank_la.exception import (
    InsufficientFundsException,
    InvalidAccountOperationException,
    LimitExceededException,
)
from ayvalikbank_la.model import Currency, Customer
from ayvalikbank_la.service import AccountService, TransferService


def _new_customer(tier: str = "STANDARD") -> Customer:
    return Customer(
        id=uuid4(),
        name="alice",
        email=f"alice-{uuid4()}@example.com",
        role="CUSTOMER",
        tier=tier,
        current_password_hash="x",
    )


async def _add_customer(session, tier: str = "STANDARD") -> UUID:
    c = _new_customer(tier)
    session.add(c)
    await session.flush()
    return c.id


@pytest.mark.asyncio
async def test_opens_checking_with_given_overdraft_limit(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    a = await svc.create_checking(cid, Currency.USD, Decimal("500"))
    assert a.type == "CHECKING"
    assert a.overdraft_limit == Decimal("500")


@pytest.mark.asyncio
async def test_opens_savings_with_given_interest_rate(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    a = await svc.create_savings(cid, Currency.USD, Decimal("0.05"))
    assert a.type == "SAVINGS"
    assert a.interest_rate == Decimal("0.05")


@pytest.mark.asyncio
async def test_opens_time_deposit_with_principal_as_balance(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    maturity = datetime.now(timezone.utc).date() + timedelta(days=365)
    a = await svc.create_time_deposit(cid, Currency.USD, Decimal("10000"), maturity, Decimal("0.05"))
    assert a.type == "TIME_DEPOSIT"
    assert a.balance == Decimal("10000")
    assert a.matured is False


@pytest.mark.asyncio
async def test_deposit_on_time_deposit_rejected(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    maturity = datetime.now(timezone.utc).date() + timedelta(days=365)
    a = await svc.create_time_deposit(cid, Currency.USD, Decimal("1000"), maturity, Decimal("0.05"))
    with pytest.raises(InvalidAccountOperationException, match="locked"):
        await svc.deposit(a.owner_id, a.id, Decimal("100"), Currency.USD)


@pytest.mark.asyncio
async def test_rejects_transfer_from_time_deposit(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    maturity = datetime.now(timezone.utc).date() + timedelta(days=365)
    src = await svc.create_time_deposit(cid, Currency.USD, Decimal("1000"), maturity, Decimal("0.05"))
    tgt = await svc.create_checking(cid, Currency.USD, Decimal("0"))
    with pytest.raises(InvalidAccountOperationException, match="do not support"):
        await svc.transfer(src.owner_id, src.id, tgt.id, Decimal("100"), Currency.USD)


@pytest.mark.asyncio
async def test_checking_allows_withdraw_into_overdraft(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    a = await svc.create_checking(cid, Currency.USD, Decimal("200"))
    await svc.deposit(a.owner_id, a.id, Decimal("100"), Currency.USD)
    await svc.withdraw(a.owner_id, a.id, Decimal("250"), Currency.USD)
    assert a.balance == Decimal("-150")


@pytest.mark.asyncio
async def test_rejects_withdraw_beyond_checking_overdraft(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    a = await svc.create_checking(cid, Currency.USD, Decimal("100"))
    with pytest.raises(InsufficientFundsException, match="overdraft"):
        await svc.withdraw(a.owner_id, a.id, Decimal("101"), Currency.USD)


@pytest.mark.asyncio
async def test_rejects_withdraw_above_standard_cap(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)  # STANDARD
    a = await svc.create_checking(cid, Currency.USD, Decimal("0"))
    await svc.deposit(a.owner_id, a.id, Decimal("10000"), Currency.USD)
    with pytest.raises(LimitExceededException, match="5000"):
        await svc.withdraw(a.owner_id, a.id, Decimal("5001"), Currency.USD)


@pytest.mark.asyncio
async def test_premium_halves_transfer_fee(session):
    svc = AccountService(session, TransferService())
    src_owner = await _add_customer(session, tier="PREMIUM")
    tgt_owner = await _add_customer(session, tier="STANDARD")
    src = await svc.create_checking(src_owner, Currency.USD, Decimal("0"))
    tgt = await svc.create_checking(tgt_owner, Currency.USD, Decimal("0"))
    await svc.deposit(src.owner_id, src.id, Decimal("1000"), Currency.USD)
    await svc.set_transfer_fee_percent(Decimal("2"))  # 2%
    await svc.transfer(src.owner_id, src.id, tgt.id, Decimal("200"), Currency.USD)
    # standard would charge 2% = 4; premium halves it = 2
    # source debited 200 + 2 = 202, started at 1000, now 798
    assert src.balance == Decimal("798.00")
    assert tgt.balance == Decimal("200")


@pytest.mark.asyncio
async def test_accrue_interest_on_savings_credits_expected(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    a = await svc.create_savings(cid, Currency.USD, Decimal("0.12"))
    await svc.deposit(a.owner_id, a.id, Decimal("1000"), Currency.USD)
    tx = await svc.accrue_interest(a.id, 2026, 4)
    # 12% / 12 = 1% monthly → 10 on 1000
    assert tx.amount == Decimal("10.00")
    assert a.balance == Decimal("1010.00")
    assert a.last_accrual_date == date(2026, 5, 1)


@pytest.mark.asyncio
async def test_accrue_on_non_savings_rejected(session):
    svc = AccountService(session, TransferService())
    cid = await _add_customer(session)
    a = await svc.create_checking(cid, Currency.USD, Decimal("0"))
    with pytest.raises(InvalidAccountOperationException, match="savings"):
        await svc.accrue_interest(a.id, 2026, 4)
