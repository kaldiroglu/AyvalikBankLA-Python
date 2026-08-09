# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Ayvalık Bank LA-Python** — Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) port of `AyvalikBankLA-JAVA` (the Java/Spring Boot layered project) and `AyvalikBankLA-NET` (the .NET port). Identical use cases, same 3-tier / anemic-model / fat-service style.

## Cross-repository invariants

This repo is one of six (hexagonal + layered × Java/.NET/Python) that must stay **functionally
identical**. `AyvalikBankContractTests` is one black-box HTTP suite run against all six, and CI runs
it on every push. Before changing any endpoint, status code, field name or JSON shape, check whether
the change belongs in all six.

- Wire format is **camelCase**; validation failures are **400** (not FastAPI's default 422).
- Enums travel as **strings** (`"USD"`), never numbers.
- Refactoring write-ups live in `Refactorings.md`; the Java hexagonal repo is the reference.
- The suite is 29 tests; all six implementations currently pass 29/29.

## Commands

```bash
# Browsable API docs once the app is running: /docs
# Shared contract suite (from AyvalikBankContractTests):
#   BANK_BASE_URL=http://localhost:8001 pytest tests/

docker compose up -d                                     # Postgres on port 5435, database ayvalikbank_la_python
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q                                      # all 51 tests
.venv/bin/uvicorn ayvalikbank_la.main:app --port 8001 --reload

# Run without Docker. --port 8001 keeps this off HA-Python's 8000.
DATABASE_URL="sqlite+aiosqlite:///./dev.db" .venv/bin/uvicorn ayvalikbank_la.main:app --port 8001
```

## Environment gotchas

- **The venv hardcodes an absolute interpreter path** — moving the repo breaks it. Recreate with
  `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- **`from __future__ import annotations` hides missing imports** until something resolves the
  annotation. A missing port import passed every test and CI, and only broke `/openapi.json`.
- **`.env` silently overrides `DEFAULT_DB_URL` in `main.py`.** `.env.example` was once wrong on
  user, password *and* port, and had been copied to a real `.env` — so the app connected to a native
  PostgreSQL on 5432 instead of its own container. Keep `.env.example` in step with
  `docker-compose.yml`; it exists to be copied.

## Ports and databases

This repo: app **8001**, PostgreSQL **5435**, database `ayvalikbank_la_python`.

All six repos take distinct application and PostgreSQL ports so every one can run at the same
time; `README.md` carries the full table. **5432 is deliberately unused** — it is the default for
a native PostgreSQL (Postgres.app, Homebrew), and an application pointed at it connects to that
server instead of its own container, with no error to say so. Every compose service sets an
explicit `container_name`: without one Compose derives a name from the directory, and a container
can outlive the checkout that defined it while still holding its port.

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

## Design Decisions (2026-08 hardening pass)

- **Ownership authorization**: every customer-facing service method takes the caller's id, taken from the authenticated principal — never from a route or query parameter. Transfers check the **source only**; the target is deliberately unchecked. Opening an account takes no owner id: the caller is the owner. See `Refactorings.md`.
- **Optimistic locking**: accounts carry a version token. A conflict surfaces at commit and maps to HTTP 409.
- **Three hexagonal refactorings deliberately do not apply here** — `TransactionAmount` (no `Money` value object), actor-shaped ports (layered has no ports) and the domain refusal vocabulary (no domain/application seam to translate across). They are artifacts of the hexagonal boundary; see `Refactorings.md`.

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
