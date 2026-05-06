# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Ayvalık Bank LA-Python** — Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) port of `AyvalikBankLA-JAVA` (the Java/Spring Boot layered project) and `AyvalikBankLA-NET` (the .NET port). Identical use cases, same 3-tier / anemic-model / fat-service style.

## Commands

```bash
docker compose up -d                                     # Postgres on port 5435
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q                                      # all 28 tests
.venv/bin/uvicorn ayvalikbank_la.main:app --reload
```

## Architecture

Classic 3-Tier Layered. Direct dependencies: Controller → Service → AsyncSession.

```
web/             — controllers (FastAPI), DTOs (Pydantic), GlobalExceptionHandler
service/         — CustomerService, AccountService, PasswordValidationService, TransferService
repository/      — DbContext (async engine + sessionmaker)
model/           — anemic SQLAlchemy entities + enums
exception/       — typed exception classes
config/          — BcryptHasher, admin_seeder
```

## Key Decisions (preserved from the Java sibling)

- **Anemic model.** Entities have mapped columns only. No business methods.
- **Business logic in services.** Status guards, balance checks, fee calc, type-specific behavior — all in `AccountService` / `CustomerService`.
- **No repository abstraction.** Services hold `AsyncSession` directly. The Python-idiomatic equivalent of holding `DbContext` (.NET) or injecting a Spring Data repo (Java) — no extra `IRepository<T>` ceremony.
- **DTO `from_entity(...)` factory methods** mirror the Java `from(Entity)` and .NET `From(entity)` patterns.
- **`Decimal` for money** matches Java's `BigDecimal` and .NET's `decimal`.
- **Single `Account` table with `Type` discriminator + nullable type-specific columns** (`overdraft_limit`, `interest_rate`, `last_accrual_date`, `principal`, `opened_on`, `maturity_date`, `matured`). `AccountService` dispatches behavior with `if account.type == AccountType.X.value` — preserving the layered/anemic style.
- **Customer tiers** as a `CustomerTier` enum + Enum methods carrying policy data: `fee_multiplier()` (1.0×/0.5×/0.0×) and per-transaction caps (5k/50k/unlimited transfer; 5k/25k/unlimited withdrawal).
- **Auth** — FastAPI `HTTPBasic`. Credentials checked against the `customers` table.

## Default Admin

`admin@ayvalikbank.dev` / `Admin@123!` (seeded by `seed_admin` on first startup, with `tier = STANDARD`)
