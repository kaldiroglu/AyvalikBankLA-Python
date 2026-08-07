"""Ownership authorization on customer-facing account operations.

Any authenticated customer could previously operate on any account given its id, and set any
other customer's password. Mirrors AyvalikBankHA-JAVA Refactorings.md entry 3.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from ayvalikbank_la.exception import UnauthorizedAccessException
from ayvalikbank_la.model import Currency, Customer
from ayvalikbank_la.service import AccountService, TransferService


async def _add_customer(session, tier: str = "STANDARD") -> UUID:
    c = Customer(
        id=uuid4(),
        name="alice",
        email=f"alice-{uuid4()}@example.com",
        role="CUSTOMER",
        tier=tier,
        current_password_hash="x",
    )
    session.add(c)
    await session.flush()
    return c.id


@pytest.mark.asyncio
async def test_deposit_into_another_customers_account_is_rejected(session):
    svc = AccountService(session, TransferService())
    a = await svc.create_checking(await _add_customer(session), Currency.USD, Decimal("0"))

    with pytest.raises(UnauthorizedAccessException):
        await svc.deposit(uuid4(), a.id, Decimal("100"), Currency.USD)


@pytest.mark.asyncio
async def test_withdrawal_from_another_customers_account_is_rejected(session):
    svc = AccountService(session, TransferService())
    a = await svc.create_checking(await _add_customer(session), Currency.USD, Decimal("0"))

    with pytest.raises(UnauthorizedAccessException):
        await svc.withdraw(uuid4(), a.id, Decimal("10"), Currency.USD)


@pytest.mark.asyncio
async def test_transfer_out_of_another_customers_account_is_rejected(session):
    svc = AccountService(session, TransferService())
    intruder = await _add_customer(session)
    src = await svc.create_checking(await _add_customer(session), Currency.USD, Decimal("0"))
    tgt = await svc.create_checking(intruder, Currency.USD, Decimal("0"))

    with pytest.raises(UnauthorizedAccessException):
        await svc.transfer(intruder, src.id, tgt.id, Decimal("10"), Currency.USD)


@pytest.mark.asyncio
async def test_reading_another_customers_balance_is_rejected(session):
    svc = AccountService(session, TransferService())
    a = await svc.create_checking(await _add_customer(session), Currency.USD, Decimal("0"))

    with pytest.raises(UnauthorizedAccessException):
        await svc.get_balance(uuid4(), a.id)


@pytest.mark.asyncio
async def test_reading_another_customers_transactions_is_rejected(session):
    svc = AccountService(session, TransferService())
    a = await svc.create_checking(await _add_customer(session), Currency.USD, Decimal("0"))

    with pytest.raises(UnauthorizedAccessException):
        await svc.get_transactions(uuid4(), a.id)


@pytest.mark.asyncio
async def test_listing_another_customers_accounts_is_rejected(session):
    svc = AccountService(session, TransferService())

    with pytest.raises(UnauthorizedAccessException):
        await svc.list_accounts(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_the_transfer_target_is_deliberately_not_ownership_checked(session):
    svc = AccountService(session, TransferService())
    sender = await _add_customer(session)
    recipient = await _add_customer(session)
    src = await svc.create_checking(sender, Currency.USD, Decimal("0"))
    tgt = await svc.create_checking(recipient, Currency.USD, Decimal("0"))
    await svc.deposit(sender, src.id, Decimal("500"), Currency.USD)

    await svc.transfer(sender, src.id, tgt.id, Decimal("100"), Currency.USD)

    amount, _ = await svc.get_balance(recipient, tgt.id)
    assert amount == Decimal("100")
