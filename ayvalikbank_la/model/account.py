from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..repository.db import Base


class Account(Base):
    """Anemic POCO entity. All business logic lives in services."""

    __tablename__ = "accounts"

    # Optimistic-lock token, managed entirely by SQLAlchemy.
    #
    # Without it two concurrent withdrawals both read the same balance, both write their own
    # result, and one silently disappears while both transaction rows persist - leaving the
    # balance disagreeing with the ledger.
    # Mirrors AyvalikBankHA-JAVA Refactorings.md entry 5.
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    # Discriminator + nullable type-specific columns
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    overdraft_limit: Mapped[Decimal | None] = mapped_column(Numeric(19, 2), nullable=True)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    last_accrual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    principal: Mapped[Decimal | None] = mapped_column(Numeric(19, 2), nullable=True)
    opened_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    matured: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __mapper_args__ = {"version_id_col": version}

