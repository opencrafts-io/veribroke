# 3. Make target_user_id optional and stop treating it as a Verisafe-specific identity

Date: 2026-07-13

## Status

accepted

## Context

Veribroke was originally built to serve the academia-ecosystem services,
which all shared a single identity space (Verisafe user IDs). The message
contract reflects that: `target_user_id` is a required field, documented
in `README.md` as *"Verisafe User Responsible For This Initiation."*

OpenCrafts has since grown beyond that ecosystem. Sharing a single
cross-service user-id space with every new integrating app isn't
feasible, and Veribroke shouldn't need to concern itself with any
particular identity system to do its job — it's a payment gateway, not
an identity provider.

Auditing every reference to `target_user_id` in the codebase
(`payments/models.py`, `payments/stkpush_mpesa/{serializers,utils}.py`)
confirms it is **write-only**: `make_mpesa_stk` copies it onto the
`Transactions` row and nothing else in Veribroke's processing logic —
STK push, callbacks, notifications, split-transaction handling — ever
reads it back. The "Verisafe user" framing was never actually enforced
or relied upon internally; it was only ever caller-supplied bookkeeping
that happened to be required and named after one specific caller's
identity system. That makes this a validation-layer problem, not a
processing-logic one — nothing about how Veribroke initiates or tracks a
payment needs to change.

## Decision

Make `target_user_id` optional everywhere, without renaming, relocating,
or dropping it:

- `StkPushSerializers.target_user_id`: `required=True` → `required=False,
  allow_blank=True`.
- `Transactions.target_user_id`: `null=False` → `null=True, blank=True`
  (migration `0009_alter_transactions_target_user_id`, additive only).
- `make_mpesa_stk`: read it with `.get('target_user_id')` instead of
  `['target_user_id']` so an omitted field doesn't `KeyError`.
- Existing clients that still send `target_user_id` are completely
  unaffected — the field still validates, still gets stored, still
  behaves exactly as before. This is a pure widening of what's accepted,
  the same expand-only shape as ADR 0001 (`reference_id`) and ADR 0002's
  queue changes.
- New integrators are told (in the new
  `docs/mpesa-integration-guide.md`) that they don't need to supply a
  `target_user_id` at all, and that if they want a caller-owned identity
  reference echoed back in notifications, `metadata` (already documented
  as opaque, already echoed back verbatim in callbacks) is the right
  place for it — no new field needed.
- The wire field name and DB column name are both left as
  `target_user_id` rather than renamed. Renaming the wire field would be
  a genuine breaking change (existing senders use that exact key); a
  same-session DB-only rename would add migration/code churn for zero
  behavioral benefit, since nothing reads the column's name except
  Django itself.
- The column itself is **not** dropped. Ops has directly queried
  `payments_transactions` with raw SQL during past incident
  investigations (see `docs/incidents/2026-03-04_veribroke_ticket_discrepancy.md`),
  so removing a column outright is a separate, higher-stakes decision
  that needs explicit sign-off, not something to bundle into a
  contract-loosening change.

Verified with new regression tests in `payments/tests.py`
(`MakeMpesaStkTargetUserIdOptionalTests`): a request omitting
`target_user_id` succeeds and persists `None`; a request that still
supplies it (simulating an existing client) persists it exactly as
before. Full suite (12 tests), `manage.py check`, and
`makemigrations --check` all pass.

## Consequences

- New integrators no longer need access to, or membership in, any
  particular cross-service identity scheme to send a valid payment
  request. This was the actual blocker for onboarding apps outside the
  original academia ecosystem.
- Zero behavior change for existing clients: nothing about the request
  or response shape changes for a caller that keeps sending
  `target_user_id`.
- `Transactions.target_user_id` can now be `NULL` going forward. No
  existing code reads it back, so there's nothing to update for `None`-
  handling -- confirmed by the write-only audit above.
- The field is not removed, so it remains available for ops'
  ad hoc/reconciliation queries against existing and future rows that do
  populate it, and old clients that never migrate off it lose nothing.
- Not addressed here (explicitly out of scope): actually removing the
  column, and any similar treatment of `sender` (the M-Pesa phone
  number) -- that field is transaction-instrument data Veribroke
  genuinely needs to process a payment, not cross-service identity data,
  and was treated as a separate concern.