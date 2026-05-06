# Architecture — Ayvalık Bank LA-Python

A Python 3.12+ port of `AyvalikBankLA-JAVA`, organized as a **Classic 3-Tier Layered Architecture**. Anemic entities, fat services, no repository abstraction.

---

## Dependency Graph

```
web (FastAPI controllers + Pydantic DTOs)
   │
   ▼
service (CustomerService, AccountService, TransferService, PasswordValidationService)
   │
   ▼
repository (DbContext = async engine + sessionmaker) — direct SQLAlchemy dependency
   │
   ▼
model (SQLAlchemy POCO entities)
```

Direct, top-down dependencies. Controllers know about services; services know about the session; the session knows about entities.

---

## Project Layout

```
ayvalikbank_la/
  model/                      — POCO entities + enums
    customer.py, account.py, transaction.py, settings.py
    account_status.py, account_type.py, customer_tier.py,
    transaction_type.py, currency.py
  repository/
    db.py                     — async engine + sessionmaker
  service/
    customer_service.py       — create/delete/list/change-password/change-tier
    account_service.py        — open per type, deposit/withdraw/transfer,
                                accrue interest, mature time deposit,
                                freeze/unfreeze/close, type-aware dispatch
    transfer_service.py       — fee calc + per-transaction limit checks
    password_validation_service.py
  web/
    customer_controller, account_controller, admin_controller
    dto.py                    — Pydantic request + response models
                                with from_entity() factories
    global_exception_handler  — register_exception_handlers(app)
    deps.py                   — FastAPI Depends + Basic Auth
  exception/
    bank_exceptions.py        — typed exception classes
  config/
    basic_auth.py             — BcryptHasher
    admin_seeder.py           — seed admin@ayvalikbank.dev on startup
  main.py                     — composition root
tests/                        — pytest tests (28)
```

---

## Key Design Decisions

### Anemic model

Entities are SQLAlchemy classes with mapped columns only — no business methods.

```python
class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    currency: Mapped[str] = mapped_column(String(8))
    balance: Mapped[Decimal] = mapped_column(Numeric(19, 2), default=0)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    type: Mapped[str] = mapped_column(String(16))
    overdraft_limit: Mapped[Decimal | None] = mapped_column(Numeric(19, 2), nullable=True)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    # ... 4 more nullable type-specific columns
```

### Fat services with type dispatch

`AccountService` uses `if account.type == AccountType.X.value` to dispatch behavior:

```python
async def withdraw(self, account_id, amount, currency):
    account = await self._require_account(account_id)
    self._ensure_operable(account)
    self._ensure_same_currency(account, currency)
    owner = await self._require_customer(account.owner_id)
    self._transfer.require_withdrawal_within_limit(amount, CustomerTier(owner.tier))

    if account.type == AccountType.TIME_DEPOSIT.value:
        if not account.matured:
            raise InvalidAccountOperationException("Time deposit has not matured")
    if account.type == AccountType.CHECKING.value:
        floor = -(account.overdraft_limit or Decimal("0"))
        if account.balance - amount < floor:
            raise InsufficientFundsException(...)
    else:
        if account.balance < amount:
            raise InsufficientFundsException("Insufficient funds")
    account.balance -= amount
    return await self._record_transaction(...)
```

### No repository abstraction

Services hold `AsyncSession` directly. The Python-idiomatic equivalent of holding `DbContext` (.NET) or `JpaRepository<T,ID>` (Java) — no extra `IRepository<T>` interface, no Unit-of-Work wrapper. SQLAlchemy is the persistence layer, full stop.

### Single-table inheritance for accounts

One `accounts` table with a `type` discriminator and seven nullable type-specific columns. Column maps live as `mapped_column(...)` annotations on the entity class.

### `CustomerTier` with policy methods on the Enum

```python
class CustomerTier(str, Enum):
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"
    PRIVATE = "PRIVATE"

    def fee_multiplier(self) -> Decimal: ...
    def max_per_transfer(self) -> Decimal | None: ...
    def max_per_withdrawal(self) -> Decimal | None: ...
```

The lookup tables live in module-level dicts keyed by `CustomerTier`.

### DTOs with `from_entity(entity)` factory methods

Each Pydantic response model exposes a `@staticmethod from_entity(entity)` — mirrors the Java sibling's `from(Entity)` pattern and the .NET sibling's `From(entity)`.

### Cross-cutting

- **Authentication** — FastAPI `HTTPBasic` security dependency; credentials read from the `customers` table.
- **Error handling** — `register_exception_handlers(app)` maps domain exceptions to RFC 7807-style `ProblemDetails` JSON: 404 not-found, 401 invalid-credentials, 422 invalid-account-operation / limit-exceeded / insufficient-funds.
- **Composition root** — `main.py`. Engine, services, exception handlers, controllers all wired here via FastAPI's `dependency_overrides`.

---

## Request Flow

### `POST /api/accounts/checking?owner_id={id}`

```
HTTP request
  → AccountController.create_checking
      → AccountService.create_checking(owner_id, currency, overdraft_limit)
          → session.get(Customer, owner_id)
          → Account(type="CHECKING", overdraft_limit=...)
          → session.add(...) + flush()
      ← AccountResponse.from_entity(account)
HTTP 201 Created + JSON
```

### `POST /api/accounts/{id}/transfer` (cross-customer, with fee)

```
HTTP request
  → AccountController.transfer
      → AccountService.transfer(source_id, target_id, amount, currency)
          → load source, target, source_owner, settings
          → TransferService.require_transfer_within_limit(amount, source_owner.tier)
          → fee = TransferService.calculate_fee(amount, same_customer, fee_pct, tier)
          → debit source by (amount + fee), credit target by amount
          → record TRANSFER_OUT and TRANSFER_IN transactions
          → flush
HTTP 200 OK
```

---

## Tech Stack

| Concern          | Technology                                  |
|------------------|---------------------------------------------|
| Runtime          | Python 3.12+                                |
| Web              | FastAPI                                     |
| Persistence      | SQLAlchemy 2.0 (async) + asyncpg            |
| Auth             | FastAPI `HTTPBasic`                         |
| Validation       | Pydantic v2                                 |
| Testing          | pytest · pytest-asyncio · aiosqlite         |
| Password hashing | bcrypt                                      |
| Local infra      | Docker Compose (Postgres on `5435`)         |

---

## Comparison to the Java/.NET Siblings

| Aspect | Java LA1 | .NET LA-NET | Python LA-Python |
|---|---|---|---|
| Entity style | Anemic JPA `@Entity` | Anemic POCO + EF Core column maps | Anemic SQLAlchemy `mapped_column` |
| Repository | Spring Data `JpaRepository<T,ID>` | None — `DbContext` directly | None — `AsyncSession` directly |
| Service | `@Service` + `@Transactional` | Plain class, scoped DI | Plain class, request-scoped session |
| Controller | `@RestController` + `@RequestMapping` | `[ApiController]` + `[Route]` | FastAPI `APIRouter` + decorators |
| Account type dispatch | `if (account.getType() == ...)` | `if (account.Type == ...)` | `if account.type == ... .value` |
| Tier policy | enum methods | extension methods | enum methods |
| Auth | Spring Security HTTP Basic | `AuthenticationHandler<>` | FastAPI `HTTPBasic` |
| Error handling | `@ControllerAdvice` | `IExceptionHandler` | `@app.exception_handler(...)` |
| Money | `BigDecimal` + `Currency` enum | `decimal` + `Currency` enum | `Decimal` + `Currency` enum |

The three sibling LA projects deliberately share many surface decisions (auth, exception handler shape, DTO factory pattern, single-table accounts) so the **architectural contrast with the HA siblings** — anemic + fat-service vs. rich-domain + ports — is the primary axis of difference.
