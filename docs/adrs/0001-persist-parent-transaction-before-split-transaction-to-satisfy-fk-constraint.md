# 1. Persist parent transaction before split transaction to satisfy FK constraint

Date: 2026-07-13

## Status

accepted

## Context

`SplitTransactions.split_id` is a `OneToOneField` to `Transactions` (PK
`request_id`), enforced by a non-deferrable Postgres foreign key.

In `payments/stkpush_mpesa/utils.py::make_mpesa_stk`, the split-transaction
branch built a `SplitTransactions` row with `split_id=trans` and called
`split_trans.save()` while `trans` (the parent `Transactions` row) had not
yet been inserted — `trans.save()` only ran later, and only after a
successful M-Pesa STK push response. Postgres checks non-deferred FK
constraints at statement execution time, not at transaction commit, so
`split_trans.save()` raised `ForeignKeyViolation` on effectively every
split-enabled request. The error was swallowed by a broad
`except Exception`, surfaced to callers as a generic
`"transaction was not successful"`, and silently broke the split-transaction
feature documented in `README.md`.

This was most likely introduced by commit `a0934ad`
("fix: removed double saving of a transaction object"), which removed an
early `trans.save()` call that had been redundant for the plain
(non-split) STK path but was load-bearing for the split path, since it's
what made the parent row exist before the child FK insert.

Reproduced locally with a regression test
(`payments/tests.py::MakeMpesaStkSplitTransactionTests`) against the
pre-fix code: every split-enabled request failed with
`django.db.utils.IntegrityError` /
`psycopg2.errors.ForeignKeyViolation: ... Key (split_id_id)=(...) is not
present in table "payments_transactions"`.

## Decision

Persist `trans` once, immediately before constructing `split_trans`, only
on the split-transaction branch (the non-split path is unchanged — it
still saves exactly once, after the STK push succeeds, preserving the
intent of `a0934ad`).

Because `trans` is now inserted before the STK push has responded,
`Transactions.reference_id` (previously `unique=True` with no `null=True`)
had to become nullable. Without that, every early-saved row would default
to `reference_id=""`, and Postgres unique indexes only allow one non-null
value — the *second* split-enabled request (or any request following one
that never reached its final save, e.g. a mid-flow exception or process
crash) would then collide on `""` and be permanently blocked. `NULL` is
also the more accurate representation of "no M-Pesa reference yet" than an
empty string. This is an additive, backward-compatible migration
(`payments/migrations/0008_alter_transactions_reference_id.py`) — it
widens a constraint and touches no data other services depend on; the
RabbitMQ message contract (exchange/queue/routing-key names, JSON field
names) is unaffected.

Because a `Transactions`/`SplitTransactions` pair can now exist in the DB
before the STK push result is known, the STK-failure branch was extended
to mark both rows `"failure"` / `"failedprocessing"` (mirroring the status
vocabulary already used elsewhere in `payments/views.py` for failed
disbursements) instead of leaving them stuck at `"pending"` forever. This
only applies when `trans.split` is true; the non-split failure path is
unchanged (no row is persisted, matching current behavior — extending
audit-trail persistence to all failed STK attempts is tracked separately
as future reliability work, not bundled into this fix).

## Consequences

- Split transactions work again: the documented feature in `README.md` is
  no longer silently broken for every request.
- Failed split-enabled STK pushes now leave an accurate, terminal audit
  trail (`"failure"` / `"failedprocessing"`) instead of a zombie
  `"pending"` row that never resolves.
- `Transactions.reference_id` is nullable going forward; any code or
  report that assumed it was always a non-empty string must handle `None`
  (checked: `StkPushCallBack`/`SplitTransCallBack` in `payments/views.py`
  already filter by `reference_id=<value>`, which simply won't match `NULL`
  rows — no change needed there).
- Non-split STK requests are untouched: still a single save after the STK
  push responds, no new DB writes, no behavior change.
- Not addressed here (deliberately out of scope, tracked as follow-up):
  non-split failed STK attempts still leave no `Transactions` row at all;
  the split-transaction "unauthenticated Safaricom callback" and
  "always-ack RabbitMQ consumer" reliability gaps identified in the same
  review remain open.