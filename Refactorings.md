# Refactorings

Claude Opus 5 (1M context) — created 2026-08-08

A log of significant refactorings applied to Ayvalık Bank LA-Python.

For further enquiry please contact Akin Kaldiroglu at akin@kaldiroglu.dev

**Relationship to the other implementations.** This repository is one of six: hexagonal and layered,
in Java, .NET and Python. Five refactorings were designed in `AyvalikBankHA-JAVA`; **only two apply
here** — see *Refactorings that do not apply* at the end, which is the most interesting part of this
file. All six are held to one HTTP contract by `AyvalikBankContractTests`.

---

## Entry 1 — Ownership authorization: a rule that could not be said

**Baseline:** `bc18097` · **Commit:** `dddc4f5`

### The symptom

Any authenticated customer could operate on any other customer's data:

- `PUT /api/customers/{customer_id}/password` took its target from the path, gated only on role.
  **Any customer could set any other customer's password, then log in as them.**
- Given an account id, any customer could deposit to it, withdraw from it, transfer out of it, and
  read its balance and transaction history.
- The account-opening endpoints took `owner_id` as a query parameter with no check.

### The tell

Unlike the Java and .NET implementations — where an `UnauthorizedAccessException` sat mapped to 403
and never thrown — **this repository had no such exception and no 403 mapping at all**. There was not
even a dead handler to hint that the rule was meant to exist. Both were added.

### The root cause

No service method took the caller, so "the caller must own this account" was **inexpressible**. A
signature declares what an operation is permitted to consider; omit something and no amount of care
downstream can restore it.

### What made this port trivial

`require_customer` **already returned the authenticated `Customer`**, and every controller discarded
it:

```python
_=Depends(require_customer),      # the caller, thrown away
```

> In four of the six implementations the caller's identity was already computed and unused. The
> vulnerability was never about missing information — the rule had no place to live at the point of
> decision.

| Situation | Technique |
|---|---|
| The resource *is* the caller's | **Delete the parameter** — `owner_id` is gone |
| The path names a customer | **Require self** |
| The path names an account | **Require ownership** |

The password check runs **before** the repository lookup, so a caller cannot learn which customer ids
exist by distinguishing 404 from 403.

### The transfer asymmetry

The caller must own the **source** only. The target is deliberately unchecked — sending money to
other people is the product — and a test pins that so the obvious hardening fails loudly.

---

## Entry 2 — Optimistic locking

**Baseline:** `dddc4f5` · **Commit:** `8a69787`

### The symptom

Two concurrent withdrawals of 50 from a balance of 100 both read 100 and both wrote 50. The balance
ended at **50** where it should be **0**, with **both** transaction rows written — money created from
nothing, ledger contradicting the account.

### Why this port was the easy one

The layered service loads through the session's identity map and mutates that instance, so
`version_id_col` alone closes the hole.

Compare the hexagonal implementations, where an adapter sits between service and ORM:
`AyvalikBankHA-JAVA` rebuilt a **detached** entity on every save; `AyvalikBankHA-NET` read with
`AsNoTracking()`, so its token would have incremented forever while catching nothing.

> **An ORM can only protect a row you actually loaded.** The mapping layer that buys the hexagonal
> repos their independence is exactly what put that claim at risk.

### A portability detail worth knowing

**SQLAlchemy's `version_id_col` starts at 1; Hibernate's `@Version` and EF's token start at 0.** The
tests assert the real value in each implementation rather than a shared assumption.

### The test needs no threads

Two sessions committing in a fixed order reproduce the bug deterministically. **A lost update is a
stale-read problem, not a timing problem.** `StaleDataError` maps to **409 Conflict** with a fixed
message rather than SQLAlchemy's, which names the table and key.

---

## Entry 3 — Speaking the same HTTP contract as the others

**Baseline:** `8a69787` · **Commit:** `99b9dbd`

`AyvalikBankContractTests` is a black-box HTTP suite run against all six implementations. Its first
run against this repository failed a third of its cases. **Not one was a flaw in the suite.**

| | Java / .NET | Python (before) |
|---|---|---|
| Request fields | `targetAccountId`, `feePercent`, `newPassword` | `target_account_id`, `fee_percent`, `new_password` |
| Validation rejection | 400 | 422 (FastAPI default) |

**A client written against the Java API could not talk to this one at all** — every request carrying
a multi-word field was rejected before reaching any business logic.

DTOs now derive from a `_CamelModel` base whose alias generator bridges snake_case Python attributes
to camelCase JSON, and a `RequestValidationError` handler returns 400. Python attribute names are
unchanged; only the wire format moved.

---

## Entry 4 — Aligning the exception vocabulary

**Commit:** `afeb015`

While porting the missing orchestration tests, six state-related rules turned out to be classified
differently here than in the other two layered implementations:

| Rule | Here (before) | LA-JAVA and LA-NET |
|---|---|---|
| "Time deposit has not matured" | `InvalidAccountOperationException` | `AccountNotOperableException` |
| "Cannot mature a closed account" | `InvalidAccountOperationException` | `AccountNotOperableException` |
| "Account is already matured" | `InvalidAccountOperationException` | `AccountNotOperableException` |
| "Maturity date not yet reached" | `InvalidAccountOperationException` | `AccountNotOperableException` |
| "Cannot accrue interest on a closed account" | `InvalidAccountOperationException` | `AccountNotOperableException` |
| maturity type check | `InvalidAccountOperationException` | `AccountNotOperableException` |

Python was the outlier, two implementations to one, and is now aligned.

**Both map to HTTP 422, so the shared contract suite could not see the difference.** That is the
honest limit of a black-box suite: it proves the six agree on *what clients observe*, not on *how
they reason internally*. Two implementations can be contract-identical and still disagree about what
kind of failure just occurred — which matters the moment someone catches a specific type, or reads
the code to learn the domain.

The two layers of testing are complementary, and neither would have found the other's bugs.

---

## Refactorings that do not apply here — and why

Three of the five refactorings from `AyvalikBankHA-JAVA` were deliberately **not** ported.

### `TransactionAmount` (HA entry 1)

It wraps a `Money` value object. **This repository has no `Money`** — amounts are raw `Decimal`
passed alongside a separate `Currency`. Introducing it would mean first introducing `Money`, moving
the layered design toward the rich domain model the hexagonal repositories exist to contrast with.

Worth noting: even in `AyvalikBankHA-Python`, where it *was* applied, the guarantee is weak.
`object.__new__` bypasses `__post_init__`, so the type is a convention rather than an invariant —
and that repository ships a test demonstrating the hole rather than implying a safety Python cannot
give.

### Actor-shaped ports (HA entry 2)

Layered architecture has no ports. Controllers call services directly.

### A refusal vocabulary (HA entry 4)

**Zero except blocks in `account_service.py`. Zero `PermissionError`. Zero message matching.**

`AyvalikBankHA-Python` needed that refactoring badly: its domain raised `PermissionError` — an
`OSError` subclass meaning *filesystem permission denied* — from 23 places, and its application layer
decided the HTTP status by running `str(e).startswith("Insufficient")`. That defect exists *because*
hexagonal separates domain from application and refusals must be translated across the seam. A
layered service raises the mapped exception directly. No seam, no defect.

### The conclusion worth teaching

**Three of the five refactorings are artifacts of the hexagonal boundary.** The layered
implementation is not behind; it is structurally incapable of those defects, and pays for it
elsewhere — an anemic model and logic concentrated in services.

That trade is the point of keeping both architectures, and it shows more clearly in what *didn't*
need fixing than in what did.

---

## Deliberate non-goals

- **`Customer` has the same lost-update exposure** as `Account`.
- **No retry-on-conflict.** A 409 tells the client to retry.
- **`change_password` does not verify the current password.** Defensible under HTTP Basic; not once
  sessions arrive.
- **No controller tests.** The web layer is covered by `AyvalikBankContractTests`, which found entry
  3 and needs a running instance.

## Discussion questions

1. Entry 3 made this API compatible with the other five. What would have happened if the *other five*
   had been changed to snake_case instead?
2. Entry 4 was invisible to the contract suite. What would catch that class of divergence?
3. Three refactorings did not apply here. For each, name the cost this architecture pays instead.
