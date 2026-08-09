# Ayvalık Bank LA-Python

A banking application built as a learning project to demonstrate **Classic 3-Tier Layered Architecture** in **Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async)**. Python counterpart to `AyvalikBankLA-JAVA` (Java/Spring Boot) and `AyvalikBankLA-NET` (.NET).

For further enquiry please contact Akin Kaldiroglu at akin@kaldiroglu.dev

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
.venv/bin/uvicorn ayvalikbank_la.main:app --port 8001 --reload
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

## Ports across the six repos

The six Ayvalık Bank implementations are meant to be compared side by side, so every one
takes its own application port and its own PostgreSQL port. All six can run at once.

| Repo | App | PostgreSQL | Database |
|---|---|---|---|
| `AyvalikBankHA-JAVA` | **8080** | **5437** | `ayvalikbank_ha_java` |
| `AyvalikBankLA-JAVA` | **8081** | **5438** | `ayvalikbank_la_java` |
| `AyvalikBankHA-NET` | **5080** | **5434** | `ayvalikbank_ha_net` |
| `AyvalikBankLA-NET` | **5050** | **5433** | `ayvalikbank_la_net` |
| `AyvalikBankHA-Python` | **8000** | **5436** | `ayvalikbank` |
| `AyvalikBankLA-Python` | **8001** | **5435** | `ayvalikbank` |

**5432 is deliberately left free** for a native PostgreSQL install (Postgres.app, Homebrew).
A container bound to it collides, and — worse — an application pointed at it connects to the
native server instead of its own container without any error to say so.

Each stack pins its port differently, because each offers a different mechanism:

| Repo | Where its port comes from |
|---|---|
| `AyvalikBankHA-JAVA` | Spring Boot's default 8080 — nothing to configure |
| `AyvalikBankLA-JAVA` | `server.port=8081` in `application.properties` |
| `AyvalikBankHA-NET` | no `launchSettings.json`, so `--urls http://localhost:5080` is **required** — without it Kestrel binds 5000 |
| `AyvalikBankLA-NET` | `AyvalikBankLA.Api/Properties/launchSettings.json` |
| `AyvalikBankHA-Python` | `--port 8000` on the uvicorn command line |
| `AyvalikBankLA-Python` | `--port 8001` on the uvicorn command line |

The two Python repos are the fragile pair: uvicorn takes its port as a launch argument and
has no configuration file to default it in, so **omitting `--port` gives both 8000** and the
second one to start fails to bind. The documented commands always pass it explicitly.
