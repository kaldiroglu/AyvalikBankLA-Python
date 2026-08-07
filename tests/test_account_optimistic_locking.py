"""Optimistic locking on accounts.

No threads, no sleeps. A lost update is a *stale-read* problem, not a timing problem, so two
sessions committing in a fixed order reproduce it deterministically.

Mirrors AyvalikBankHA-JAVA Refactorings.md entry 5.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm.exc import StaleDataError

from ayvalikbank_la.model import Account, AccountStatus, AccountType, Currency
from ayvalikbank_la.repository.db import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


def _account() -> Account:
    return Account(
        id=uuid4(),
        owner_id=uuid4(),
        currency=Currency.USD.value,
        balance=Decimal("100"),
        status=AccountStatus.ACTIVE.value,
        type=AccountType.CHECKING.value,
        overdraft_limit=Decimal("0"),
    )


@pytest.mark.asyncio
async def test_new_account_starts_at_version_zero(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    a = _account()
    async with Session() as s:
        s.add(a)
        await s.commit()
    async with Session() as s:
        loaded = await s.get(Account, a.id)
        assert loaded.version == 1  # SQLAlchemy starts version_id_col at 1


@pytest.mark.asyncio
async def test_version_increments_on_each_update(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    a = _account()
    async with Session() as s:
        s.add(a)
        await s.commit()

    for expected in (2, 3):
        async with Session() as s:
            loaded = await s.get(Account, a.id)
            loaded.balance = Decimal(f"10{expected}")
            await s.commit()
        async with Session() as s:
            assert (await s.get(Account, a.id)).version == expected


@pytest.mark.asyncio
async def test_second_writer_is_rejected_when_both_loaded_the_same_version(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    a = _account()
    async with Session() as s:
        s.add(a)
        await s.commit()

    s1 = Session()
    s2 = Session()
    # Both read balance 100 at the same version — this is the stale read.
    first = await s1.get(Account, a.id)
    second = await s2.get(Account, a.id)

    first.balance = Decimal("50")
    await s1.commit()

    second.balance = Decimal("50")
    with pytest.raises(StaleDataError):
        await s2.commit()

    await s1.close()
    await s2.close()

    # Without the version both writers would have stored 50 and one withdrawal would be lost.
    async with Session() as s:
        assert (await s.get(Account, a.id)).balance == Decimal("50")
