# Ayvalık Bank LA-Python

A banking application built as a learning project to demonstrate **Classic 3-Tier Layered Architecture** in **Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async)**. Python counterpart to `AyvalikBankLA1` (Java/Spring Boot) and `AyvalikBankLA-NET` (.NET).

## Tech Stack

| Concern          | Technology                                    |
|------------------|----------------------------------------------|
| Runtime          | Python 3.12+                                 |
| Web              | FastAPI                                      |
| Persistence      | SQLAlchemy 2.0 (async) + asyncpg (PostgreSQL)|
| Auth             | FastAPI HTTP Basic                           |
| Validation       | Pydantic v2                                  |
| Testing          | pytest · pytest-asyncio · aiosqlite          |
| Password hashing | bcrypt                                       |
| Local infra      | Docker Compose (PostgreSQL on `5435`)        |

## Quick Start

```bash
docker compose up -d
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn ayvalikbank_la.main:app --reload
```

Default admin: `admin@ayvalikbank.dev` / `Admin@123!` (seeded on first startup)

## Project Layout

```
ayvalikbank_la/
  model/               — anemic POCO entities (SQLAlchemy classes) + enums
  repository/          — DbContext (async engine + sessionmaker)
  service/             — fat services with all business logic
  web/                 — FastAPI controllers + Pydantic DTOs +
                         GlobalExceptionHandler
  exception/           — typed exception classes
  config/              — BcryptHasher, admin_seeder
  main.py              — composition root (DI + middleware wiring)
tests/                 — pytest tests (28)
```

## Architectural notes

- **Anemic entities** — `Customer`, `Account`, `Transaction` are SQLAlchemy classes with mapped columns and **no business methods**.
- **Fat services** — `CustomerService` and `AccountService` own all business logic, including type-specific dispatch (`if account.type == AccountType.X`).
- **Single `Account` table with `Type` discriminator + nullable type-specific columns** (overdraft, interest rate, principal, maturity date, etc.) — preserves the layered/anemic style.
- **Customer tiers** (`STANDARD / PREMIUM / PRIVATE`) on `Customer`, with policy methods on the enum: `fee_multiplier()` (1.0×/0.5×/0.0×) and per-transaction caps.
- **No repository abstraction** — services depend on `AsyncSession` directly (the .NET-idiomatic equivalent of holding `DbContext`; the Java-idiomatic equivalent of injecting `JpaRepository<T,ID>`).
- **`Decimal` for money** — same precision discipline as Java's `BigDecimal` and .NET's `decimal`.

## Endpoints

| Method | Path | Role |
|---|---|---|
| POST | `/api/admin/customers` | ADMIN |
| DELETE | `/api/admin/customers/{id}` | ADMIN |
| GET | `/api/admin/customers` | ADMIN |
| PUT | `/api/admin/settings/transfer-fee` | ADMIN |
| PUT | `/api/admin/accounts/{id}/freeze` | ADMIN |
| PUT | `/api/admin/accounts/{id}/unfreeze` | ADMIN |
| PUT | `/api/admin/accounts/{id}/close` | ADMIN |
| PUT | `/api/admin/customers/{id}/tier` | ADMIN |
| PUT | `/api/admin/accounts/{id}/accrue-interest` | ADMIN |
| PUT | `/api/admin/accounts/{id}/mature` | ADMIN |
| PUT | `/api/customers/{id}/password` | CUSTOMER |
| POST | `/api/accounts/checking?owner_id=` | CUSTOMER |
| POST | `/api/accounts/savings?owner_id=` | CUSTOMER |
| POST | `/api/accounts/time-deposit?owner_id=` | CUSTOMER |
| GET | `/api/customers/{id}/accounts` | CUSTOMER |
| GET | `/api/accounts/{id}/balance` | CUSTOMER |
| POST | `/api/accounts/{id}/deposit` | CUSTOMER |
| POST | `/api/accounts/{id}/withdraw` | CUSTOMER |
| POST | `/api/accounts/{id}/transfer` | CUSTOMER |
| GET | `/api/accounts/{id}/transactions` | CUSTOMER |

## Test coverage

28 tests (pytest), covering:
- TransferService tier-aware fees and per-transaction limits
- CustomerTier policy data
- AccountService against SQLite in-memory: opens per type, time-deposit deposit/transfer rejection, checking overdraft happy + cap rejection, tier-cap rejection, premium fee discount, savings monthly accrual.
