from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exception import (
    InvalidCredentialsException,
    NotFoundException,
    PasswordReuseException,
)
from ..model import Customer, CustomerTier
from ..model.customer import PasswordHistory
from .password_validation_service import PasswordValidationService

_PASSWORD_HISTORY_LIMIT = 3


class CustomerService:
    def __init__(
        self,
        session: AsyncSession,
        hasher,
        password_validator: PasswordValidationService,
    ) -> None:
        self._session = session
        self._hasher = hasher
        self._validator = password_validator

    async def create_customer(self, name: str, email: str, password: str) -> Customer:
        self._validator.validate(password)
        existing = await self._session.execute(
            select(Customer).where(Customer.email == email)
        )
        if existing.scalar_one_or_none() is not None:
            raise InvalidCredentialsException(f"Email already in use: {email}")
        c = Customer(
            id=uuid4(),
            name=name,
            email=email,
            role="CUSTOMER",
            tier=CustomerTier.STANDARD.value,
            current_password_hash=self._hasher.hash(password),
        )
        self._session.add(c)
        await self._session.flush()
        return c

    async def delete_customer(self, customer_id: UUID) -> None:
        c = await self._session.get(Customer, customer_id)
        if c is None:
            raise NotFoundException(f"Customer {customer_id} not found")
        await self._session.execute(
            delete(PasswordHistory).where(PasswordHistory.customer_id == customer_id)
        )
        await self._session.delete(c)
        await self._session.flush()

    async def list_customers(self) -> list[Customer]:
        result = await self._session.execute(select(Customer))
        return list(result.scalars().all())

    async def change_password(self, customer_id: UUID, new_password: str) -> None:
        self._validator.validate(new_password)
        c = await self._session.get(Customer, customer_id)
        if c is None:
            raise NotFoundException(f"Customer {customer_id} not found")
        history = await self._session.execute(
            select(PasswordHistory)
            .where(PasswordHistory.customer_id == customer_id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(_PASSWORD_HISTORY_LIMIT)
        )
        history_hashes = [h.password_hash for h in history.scalars().all()]
        for h in [c.current_password_hash, *history_hashes]:
            if self._hasher.matches(new_password, h):
                raise PasswordReuseException("Password was used recently")
        old_hash = c.current_password_hash
        c.current_password_hash = self._hasher.hash(new_password)
        self._session.add(
            PasswordHistory(
                customer_id=customer_id,
                password_hash=old_hash,
                created_at=datetime.now(timezone.utc),
            )
        )
        # Trim history
        all_history = await self._session.execute(
            select(PasswordHistory)
            .where(PasswordHistory.customer_id == customer_id)
            .order_by(PasswordHistory.created_at.desc())
        )
        rows = list(all_history.scalars().all())
        for stale in rows[_PASSWORD_HISTORY_LIMIT:]:
            await self._session.delete(stale)
        await self._session.flush()

    async def change_customer_tier(self, customer_id: UUID, new_tier: CustomerTier) -> None:
        c = await self._session.get(Customer, customer_id)
        if c is None:
            raise NotFoundException(f"Customer {customer_id} not found")
        c.tier = new_tier.value
        await self._session.flush()
