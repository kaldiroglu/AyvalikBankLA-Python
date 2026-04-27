from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..model import Customer

ADMIN_EMAIL = "admin@ayvalikbank.dev"
ADMIN_PASSWORD = "Admin@123!"


async def seed_admin(session: AsyncSession, hasher) -> None:
    existing = await session.execute(select(Customer).where(Customer.email == ADMIN_EMAIL))
    if existing.scalar_one_or_none() is not None:
        return
    session.add(
        Customer(
            id=uuid4(),
            name="Administrator",
            email=ADMIN_EMAIL,
            role="ADMIN",
            tier="STANDARD",
            current_password_hash=hasher.hash(ADMIN_PASSWORD),
        )
    )
    await session.commit()
