# Tests — Ayvalık Bank LA-Python

**Stack:** pytest · pytest-asyncio · aiosqlite (for service tests)
**Total:** 28 tests · 100% passing
**Run:** `.venv/bin/pytest -q`

The split mirrors the layered architecture: stateless services (`PasswordValidationService`, `TransferService`) get pure unit tests; stateful services that touch the session (`AccountService`) get SQLite in-memory tests so the `if account.type == X` dispatch is covered against the actual schema.

---

## Summary by Test File

| File | Tests | Style | Focus |
|---|---:|---|---|
| `test_password_validation_service.py` | 6 | pure unit | Length (×2 parametrized), digit, uppercase, special-char rules |
| `test_customer_tier.py` | 3 | pure unit | `CustomerTier` policy data |
| `test_transfer_service.py` | 8 | pure unit | Tier-aware `calculate_fee`; per-transaction limit checks |
| `test_account_service.py` | 11 | SQLite in-memory | Open per type, type-specific behavior, tier interaction |

---

## Coverage by Concern

### `PasswordValidationService`
- `accepts_valid_password`
- `rejects_out_of_range_length` (parametrized: `Short1!`, `ThisIsWayTooLong1!`)
- `rejects_missing_digit`, `rejects_missing_uppercase`, `rejects_missing_special_character`

### `CustomerTier`
- `standard_has_full_fee_and_modest_caps` — 1.0× / 5k caps
- `premium_halves_fee_and_raises_caps` — 0.5× / 50k transfer / 25k withdrawal
- `private_is_free_and_unlimited` — 0.0× / `None` caps

### `TransferService`
- `same_customer_transfer_is_free_regardless_of_tier`
- `standard_tier_pays_full_fee`, `premium_tier_pays_half_fee`, `private_tier_pays_no_fee`
- `rejects_transfer_above_standard_cap`, `allows_transfer_at_exactly_the_cap`
- `private_tier_transfer_is_unlimited`
- `rejects_withdrawal_above_premium_cap`

### `AccountService` (SQLite in-memory)
- `opens_checking_with_given_overdraft_limit`
- `opens_savings_with_given_interest_rate`
- `opens_time_deposit_with_principal_as_balance`
- `deposit_on_time_deposit_rejected`
- `rejects_transfer_from_time_deposit`
- `checking_allows_withdraw_into_overdraft` — negative balance allowed within overdraft
- `rejects_withdraw_beyond_checking_overdraft`
- `rejects_withdraw_above_standard_cap`
- `premium_halves_transfer_fee` — cross-customer transfer where source is PREMIUM
- `accrue_interest_on_savings_credits_expected`
- `accrue_on_non_savings_rejected`

The session fixture (`tests/conftest.py`) creates an aiosqlite in-memory engine, runs `Base.metadata.create_all`, and yields an `AsyncSession`. This means the column maps in the model are exercised on the same schema the production Postgres adapter sees, and the `if account.type == ...` dispatch in `AccountService` is tested end-to-end through real SQLAlchemy save/load cycles.

---

## Known Gaps

- **No controller / web tests.** Controllers, request validation, and `register_exception_handlers` are not exercised. `httpx.AsyncClient` against the FastAPI app + SQLite is a planned add.
- **No `CustomerService` tests.** Create / list / delete / change-password / change-tier paths would benefit from the same SQLite pattern.
- **No coverage tooling.** Adding `pytest --cov=ayvalikbank_la` would mirror the Java sibling's JaCoCo report.

---

## How to Run

```bash
.venv/bin/pytest -q                                            # all tests
.venv/bin/pytest tests/test_account_service.py                 # single file
.venv/bin/pytest -k "premium"                                  # by keyword
.venv/bin/pytest -v                                            # verbose
```
