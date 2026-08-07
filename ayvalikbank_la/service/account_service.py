from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exception import (
    AccountNotOperableException,
    InsufficientFundsException,
    UnauthorizedAccessException,
    InvalidAccountOperationException,
    NotFoundException,
)
from ..model import (
    Account,
    AccountStatus,
    AccountType,
    Currency,
    Customer,
    CustomerTier,
    Settings,
    Transaction,
    TransactionType,
)
from .transfer_service import TransferService

_TRANSFER_FEE_KEY = "transfer_fee_percent"


class AccountService:
    """Fat service. Type dispatch via if/else on Account.type."""

    def __init__(self, session: AsyncSession, transfer_service: TransferService) -> None:
        self._session = session
        self._transfer = transfer_service

    # ── opens ────────────────────────────────────────────────────────────

    async def create_checking(
        self, caller_id: UUID, currency: Currency, overdraft_limit: Decimal | None
    ) -> Account:
        await self._require_customer(caller_id)
        a = Account(
            id=uuid4(),
            owner_id=caller_id,
            currency=currency.value,
            balance=Decimal("0"),
            status=AccountStatus.ACTIVE.value,
            type=AccountType.CHECKING.value,
            overdraft_limit=overdraft_limit if overdraft_limit is not None else Decimal("0"),
        )
        if a.overdraft_limit < Decimal("0"):
            raise InvalidAccountOperationException("Overdraft limit cannot be negative")
        self._session.add(a)
        await self._session.flush()
        return a

    async def create_savings(
        self, caller_id: UUID, currency: Currency, annual_interest_rate: Decimal
    ) -> Account:
        await self._require_customer(caller_id)
        if annual_interest_rate < Decimal("0"):
            raise InvalidAccountOperationException("Annual interest rate must be non-negative")
        a = Account(
            id=uuid4(),
            owner_id=caller_id,
            currency=currency.value,
            balance=Decimal("0"),
            status=AccountStatus.ACTIVE.value,
            type=AccountType.SAVINGS.value,
            interest_rate=annual_interest_rate,
            last_accrual_date=None,
        )
        self._session.add(a)
        await self._session.flush()
        return a

    async def create_time_deposit(
        self,
        caller_id: UUID,
        currency: Currency,
        principal: Decimal,
        maturity_date: date,
        annual_interest_rate: Decimal,
    ) -> Account:
        await self._require_customer(caller_id)
        if principal <= Decimal("0"):
            raise InvalidAccountOperationException("Principal must be positive")
        if annual_interest_rate < Decimal("0"):
            raise InvalidAccountOperationException("Annual interest rate must be non-negative")
        opened_on = datetime.now(timezone.utc).date()
        if maturity_date <= opened_on:
            raise InvalidAccountOperationException("Maturity date must be after opened-on date")
        a = Account(
            id=uuid4(),
            owner_id=caller_id,
            currency=currency.value,
            balance=principal,
            status=AccountStatus.ACTIVE.value,
            type=AccountType.TIME_DEPOSIT.value,
            principal=principal,
            opened_on=opened_on,
            maturity_date=maturity_date,
            interest_rate=annual_interest_rate,
            matured=False,
        )
        self._session.add(a)
        await self._session.flush()
        return a

    # ── money ops ────────────────────────────────────────────────────────

    async def deposit(self, caller_id: UUID, account_id: UUID, amount: Decimal, currency: Currency) -> Transaction:
        account = await self._require_account(account_id)
        self._require_owner(account, caller_id)
        self._ensure_operable(account)
        self._ensure_same_currency(account, currency)
        if amount <= Decimal("0"):
            raise InvalidAccountOperationException("Deposit amount must be positive")
        if account.type == AccountType.TIME_DEPOSIT.value:
            raise InvalidAccountOperationException(
                "Time deposit principal is locked — further deposits are not allowed"
            )
        account.balance += amount
        return await self._record_transaction(
            account.id, TransactionType.DEPOSIT, amount, currency, "Deposit"
        )

    async def withdraw(self, caller_id: UUID, account_id: UUID, amount: Decimal, currency: Currency) -> Transaction:
        account = await self._require_account(account_id)
        self._require_owner(account, caller_id)
        self._ensure_operable(account)
        self._ensure_same_currency(account, currency)
        if amount <= Decimal("0"):
            raise InvalidAccountOperationException("Withdrawal amount must be positive")
        owner = await self._require_customer(account.owner_id)
        self._transfer.require_withdrawal_within_limit(amount, CustomerTier(owner.tier))

        if account.type == AccountType.TIME_DEPOSIT.value:
            if not account.matured:
                raise InvalidAccountOperationException("Time deposit has not matured")
        if account.type == AccountType.CHECKING.value:
            floor = -(account.overdraft_limit or Decimal("0"))
            if account.balance - amount < floor:
                raise InsufficientFundsException(
                    "Insufficient funds" if account.overdraft_limit == 0 else
                    "Withdrawal exceeds overdraft limit"
                )
        else:
            if account.balance < amount:
                raise InsufficientFundsException("Insufficient funds")
        account.balance -= amount
        return await self._record_transaction(
            account.id, TransactionType.WITHDRAWAL, amount, currency, "Withdrawal"
        )

    async def transfer(
        self,
        caller_id: UUID,
        source_id: UUID,
        target_id: UUID,
        amount: Decimal,
        currency: Currency,
    ) -> None:
        if source_id == target_id:
            raise InvalidAccountOperationException("Cannot transfer to the same account")
        source = await self._require_account(source_id)
        self._require_owner(source, caller_id)
        # The TARGET is deliberately NOT ownership-checked: sending money to another
        # customer is the entire point of a transfer.
        target = await self._require_account(target_id)
        self._ensure_operable(source)
        self._ensure_operable(target)
        self._ensure_same_currency(source, currency)
        self._ensure_same_currency(target, currency)
        if amount <= Decimal("0"):
            raise InvalidAccountOperationException("Transfer amount must be positive")
        if source.type == AccountType.TIME_DEPOSIT.value:
            raise InvalidAccountOperationException(
                "Time deposit accounts do not support transfers"
            )
        if target.type == AccountType.TIME_DEPOSIT.value:
            raise InvalidAccountOperationException(
                "Time deposit principal is locked — further deposits are not allowed"
            )
        owner = await self._require_customer(source.owner_id)
        self._transfer.require_transfer_within_limit(amount, CustomerTier(owner.tier))
        same_customer = source.owner_id == target.owner_id
        fee_pct = await self._get_transfer_fee_percent()
        fee = self._transfer.calculate_fee(amount, same_customer, fee_pct, CustomerTier(owner.tier))
        total_debit = amount + fee
        if source.type == AccountType.CHECKING.value:
            floor = -(source.overdraft_limit or Decimal("0"))
            if source.balance - total_debit < floor:
                raise InsufficientFundsException("Insufficient funds for transfer including fee")
        else:
            if source.balance < total_debit:
                raise InsufficientFundsException("Insufficient funds for transfer including fee")

        source.balance -= total_debit
        target.balance += amount

        out_desc = f"Transfer out to {target.id}" + (f" (fee: {fee})" if fee > 0 else "")
        await self._record_transaction(
            source.id, TransactionType.TRANSFER_OUT, amount, currency, out_desc
        )
        await self._record_transaction(
            target.id, TransactionType.TRANSFER_IN, amount, currency, f"Transfer in from {source.id}"
        )

    # ── reads ────────────────────────────────────────────────────────────

    async def get_balance(self, caller_id: UUID, account_id: UUID) -> tuple[Decimal, Currency]:
        a = await self._require_account(account_id)
        self._require_owner(a, caller_id)
        return a.balance, Currency(a.currency)

    async def list_accounts(self, caller_id: UUID, customer_id: UUID) -> list[Account]:
        self._require_self(customer_id, caller_id)
        await self._require_customer(customer_id)
        result = await self._session.execute(
            select(Account).where(Account.owner_id == customer_id)
        )
        return list(result.scalars().all())

    async def get_transactions(self, caller_id: UUID, account_id: UUID) -> list[Transaction]:
        self._require_owner(await self._require_account(account_id), caller_id)
        result = await self._session.execute(
            select(Transaction)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.timestamp.desc())
        )
        return list(result.scalars().all())

    # ── status transitions ──────────────────────────────────────────────

    async def freeze_account(self, account_id: UUID) -> None:
        a = await self._require_account(account_id)
        if a.status == AccountStatus.CLOSED.value:
            raise AccountNotOperableException("Cannot freeze a closed account")
        if a.status == AccountStatus.FROZEN.value:
            raise AccountNotOperableException("Account is already frozen")
        a.status = AccountStatus.FROZEN.value
        await self._session.flush()

    async def unfreeze_account(self, account_id: UUID) -> None:
        a = await self._require_account(account_id)
        if a.status == AccountStatus.CLOSED.value:
            raise AccountNotOperableException("Cannot unfreeze a closed account")
        if a.status != AccountStatus.FROZEN.value:
            raise AccountNotOperableException("Account is not frozen")
        a.status = AccountStatus.ACTIVE.value
        await self._session.flush()

    async def close_account(self, account_id: UUID) -> None:
        a = await self._require_account(account_id)
        if a.status == AccountStatus.CLOSED.value:
            raise AccountNotOperableException("Account is already closed")
        a.status = AccountStatus.CLOSED.value
        await self._session.flush()

    # ── interest / maturity ─────────────────────────────────────────────

    async def accrue_interest(self, account_id: UUID, year: int, month: int) -> Transaction:
        a = await self._require_account(account_id)
        if a.type != AccountType.SAVINGS.value:
            raise InvalidAccountOperationException(
                "Interest accrual only applies to savings accounts"
            )
        if a.status == AccountStatus.CLOSED.value:
            raise InvalidAccountOperationException("Cannot accrue interest on a closed account")
        first_of_next_month = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        if a.last_accrual_date is not None and first_of_next_month <= a.last_accrual_date:
            raise InvalidAccountOperationException(
                f"Interest already accrued for or after {year:04d}-{month:02d}"
            )
        monthly_rate = (a.interest_rate or Decimal("0")) / Decimal(12)
        interest = (a.balance * monthly_rate).quantize(Decimal("0.01"))
        a.balance += interest
        a.last_accrual_date = first_of_next_month
        return await self._record_transaction(
            a.id,
            TransactionType.INTEREST,
            interest,
            Currency(a.currency),
            f"Interest accrual for {year:04d}-{month:02d}",
        )

    async def mature_time_deposit(self, account_id: UUID) -> Transaction:
        a = await self._require_account(account_id)
        if a.type != AccountType.TIME_DEPOSIT.value:
            raise InvalidAccountOperationException(
                "Maturity only applies to time deposit accounts"
            )
        if a.status == AccountStatus.CLOSED.value:
            raise InvalidAccountOperationException("Cannot mature a closed account")
        if a.matured:
            raise InvalidAccountOperationException("Account is already matured")
        today = datetime.now(timezone.utc).date()
        if today < a.maturity_date:
            raise InvalidAccountOperationException("Maturity date not yet reached")
        months = (a.maturity_date.year - a.opened_on.year) * 12 + (
            a.maturity_date.month - a.opened_on.month
        )
        years = Decimal(months) / Decimal(12)
        interest = (a.principal * (a.interest_rate or Decimal("0")) * years).quantize(Decimal("0.01"))
        a.balance += interest
        a.matured = True
        return await self._record_transaction(
            a.id, TransactionType.INTEREST, interest, Currency(a.currency), "Maturity interest credit"
        )

    # ── admin: settings ─────────────────────────────────────────────────

    async def set_transfer_fee_percent(self, percent: Decimal) -> None:
        if percent < Decimal("0") or percent > Decimal("100"):
            raise InvalidAccountOperationException("Transfer fee percent must be between 0 and 100")
        existing = await self._session.get(Settings, _TRANSFER_FEE_KEY)
        if existing is None:
            self._session.add(Settings(key=_TRANSFER_FEE_KEY, value=str(percent)))
        else:
            existing.value = str(percent)
        await self._session.flush()

    # ── helpers ──────────────────────────────────────────────────────────

    async def _get_transfer_fee_percent(self) -> Decimal:
        e = await self._session.get(Settings, _TRANSFER_FEE_KEY)
        return Decimal(e.value) if e else Decimal("0")

    @staticmethod
    def _require_owner(account: Account, caller_id: UUID) -> None:
        """The caller must own the account. See AyvalikBankHA-JAVA Refactorings.md entry 3."""
        if account.owner_id != caller_id:
            raise UnauthorizedAccessException("Account does not belong to the caller")

    @staticmethod
    def _require_self(subject: UUID, caller_id: UUID) -> None:
        if subject != caller_id:
            raise UnauthorizedAccessException("Callers may only act on their own customer record")

    async def _require_account(self, account_id: UUID) -> Account:
        a = await self._session.get(Account, account_id)
        if a is None:
            raise NotFoundException(f"Account {account_id} not found")
        return a

    async def _require_customer(self, customer_id: UUID) -> Customer:
        c = await self._session.get(Customer, customer_id)
        if c is None:
            raise NotFoundException(f"Customer {customer_id} not found")
        return c

    @staticmethod
    def _ensure_operable(a: Account) -> None:
        if a.status == AccountStatus.FROZEN.value:
            raise AccountNotOperableException("Account is frozen")
        if a.status == AccountStatus.CLOSED.value:
            raise AccountNotOperableException("Account is closed")

    @staticmethod
    def _ensure_same_currency(a: Account, currency: Currency) -> None:
        if a.currency != currency.value:
            raise InvalidAccountOperationException(
                f"Currency {currency.value} does not match account currency {a.currency}"
            )

    async def _record_transaction(
        self,
        account_id: UUID,
        type_: TransactionType,
        amount: Decimal,
        currency: Currency,
        description: str,
    ) -> Transaction:
        t = Transaction(
            id=uuid4(),
            account_id=account_id,
            type=type_.value,
            amount=amount,
            currency=currency.value,
            timestamp=datetime.now(timezone.utc),
            description=description,
        )
        self._session.add(t)
        await self._session.flush()
        return t
