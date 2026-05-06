# Enhancement Walkthrough — Daily Withdrawal Limits

A teaching example: add **per-account, per-calendar-day cumulative withdrawal limits** to the project, then study where the change lands.

This file describes the feature in this codebase (Python 3.12+ / FastAPI / SQLAlchemy 2.0 async / 3-tier layered). Sibling files in `AyvalikBankHA-JAVA`, `AyvalikBankLA-JAVA`, `AyvalikBankHA-NET`, `AyvalikBankLA-NET`, `AyvalikBankHA-Python` describe the same feature in their respective stacks so the impact can be compared side by side.

---

## The Feature

- Each `Account` carries a nullable `daily_withdrawal_limit: Decimal | None`. None = use a tier-derived default.
- Cumulative withdrawals (direct withdraw + the debit side of transfers) on a single UTC calendar day must not exceed that limit.
- Admin can set/clear the limit per account: `PUT /api/admin/accounts/{id}/daily-limit`.
- Reset at UTC midnight.
- A separate, additive constraint — the existing per-transaction tier caps still apply.

---

## Why this feature is good for teaching

It crosses every layer: model, repository, service, controller, validation. It introduces **state that lives across transactions** ("today's running total"), which is the interesting persistence question. And it sits at the intersection of `Customer`, `Account`, and `Transaction` — three aggregates — which is where the layered/anemic style starts to feel cramped.

---

## Impact on this project — Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Layered

### Files to add or modify

| # | Layer | Path | Change |
|---|---|---|---|
| 1 | Model | `model/account.py` | Add `daily_withdrawal_limit: Mapped[Decimal | None] = mapped_column(Numeric(19, 2), nullable=True)` — anemic, no method |
| 2 | Service | `service/account_service.py` (`withdraw`) | **Inline** the SQLAlchemy aggregate query, the comparison, the `raise InsufficientFundsException(...)` (or new `DailyLimitExceededException`) into the existing method — interleaved with the existing overdraft / time-deposit / tier-cap branches |
| 3 | Service | `service/account_service.py` (`transfer`) | Same inline insertion on the source-account debit path |
| 4 | Service | `service/account_service.py` (`set_daily_withdrawal_limit`) *(new method)* | Loads account → mutates field → flush |
| 5 | Web | `web/admin_controller.py` | New `PUT /api/admin/accounts/{id}/daily-limit` endpoint |
| 6 | Web | `web/dto.py` | Add `class SetDailyLimitRequest(BaseModel)` with `Field(ge=0)` |
| 7 | Exception | `exception/bank_exceptions.py` *(optional)* | `DailyLimitExceededException` subclass of `InsufficientFundsException` so the handler still maps to 422 |
| 8 | Tests | `tests/test_account_service.py` | Extend with at-limit, just-over-limit, and after-midnight-reset cases — **must use the SQLite in-memory `session` fixture** |
| 9 | Tests | (controller tests when added) | New endpoint shape + 422 path |

### Tech-stack-specific notes (Python)

- **Anemic POCO** — adding `Mapped[Decimal | None] = mapped_column(Numeric(19, 2), nullable=True)` is a one-liner. No method on the entity. The rule lives in the service.
- **No new column-map call elsewhere** — the column is part of the `Account` mapped class itself; SQLAlchemy 2.0's `mapped_column` carries both the Python type and the DDL type in one declaration.
- **SQLAlchemy 2.0 async aggregate** inside the service:
  ```python
  from sqlalchemy import func, select
  start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
  end = start + timedelta(days=1)
  result = await self._session.execute(
      select(func.coalesce(func.sum(Transaction.amount), 0))
      .where(Transaction.account_id == account.id)
      .where(Transaction.type == TransactionType.WITHDRAWAL.value)
      .where(Transaction.timestamp >= start, Transaction.timestamp < end)
  )
  withdrawn_today = Decimal(result.scalar_one())
  ```
  This is wedged into `withdraw` *between* the overdraft branch and the tier-cap branch.
- **The `withdraw` method now has four branches**: overdraft, time-deposit-not-matured, tier cap, daily cap. Each was added separately; they accumulate.
- **No DI rewiring needed** — `AccountService.__init__` already takes `AsyncSession`; you just call a new query on it. **Faster to land than the HA-Python version.**
- **No new use-case Protocol** — there's no use-case interface concept here; the new admin operation is just a new method on `AccountService` + a controller route.
- **Exception mapping** — `register_exception_handlers(app)` already maps `LimitExceededException → 422`; reuse it (or derive a more specific exception).

### Test impact

- **You cannot write a pure-unit test for the daily-limit rule in this architecture.** The rule is the SQLAlchemy aggregate query plus the comparison plus the `if`-check plus the `raise`, all sitting inside an `async` service method bound to a session. To test it, you need the existing `session` fixture (`tests/conftest.py` already provides one over `aiosqlite`) and you need to seed prior `WITHDRAWAL` rows so the `func.sum` returns a non-zero value.
- Compare against the HA-Python sibling's `test_withdrawal_policy_service.py` — pure pytest, no async, no DB. That difference is the cost of the inlined approach.
- Existing service tests that simulated `AccountService` paths now need to insert `Transaction` rows in their setup so the new aggregate query has something to sum.

---

## Lesson Plan (apply to all six projects)

1. **Show both diffs side by side.** Count files; count *lines where the actual rule lives*.
2. **Change the rule** — "reset at customer's local midnight, not UTC." In HA you change one method on a domain service + one query in the adapter. In LA you edit a long `withdraw` that's already doing five other things; the change is wedged between the overdraft branch and the time-deposit-matured branch.
3. **Add a second consumer** — `GET /api/accounts/{id}/today-summary` showing withdrawn-so-far + remaining-limit. In HA: one controller method calling the existing port + policy. In LA: copy the SQLAlchemy `func.sum` query + comparison into a new service method.

The moral: **architecture is a bet about which kinds of change are likely.** Layered bets on rules being stable and local — it pays an entanglement tax later. The same feature shows the bet clearly.
