# 2. Bounded retry with dead-letter queue for the RabbitMQ consumer instead of always-ack

Date: 2026-07-13

## Status

accepted

## Context

`rabbit/consumers.py::ConsumerListener.callback` always called
`channel.basic_ack()` at the end, regardless of what `cons_func` (e.g.
`make_mpesa_stk`) returned. Two distinct problems followed from that:

1. A **business-logic failure** returned normally (`success=False`, e.g.
   Daraja briefly unavailable) was acked and the message discarded
   forever, with no distinction between "permanently invalid request" and
   "transient upstream blip worth retrying".
2. An **unhandled exception** inside `cons_func` (DB connection drop, an
   unexpected payload shape, etc.) meant `basic_ack` was never reached.
   The message wasn't explicitly nacked either, so it stayed unacked and
   was only redelivered when the connection eventually dropped — with no
   bound, no backoff, and (with `prefetch_count=1`) the single consumer
   thread stuck retrying the same message indefinitely on every
   reconnect. A deterministic bug in message processing becomes an
   unbounded, invisible retry loop ("poison message").

Veribroke is OpenCrafts Interactive's payment/billing/settlement
infrastructure; silently losing a payment request, or livelocking on one,
is a direct reliability risk, not just a code-quality issue.

## Decision

Give unhandled exceptions from `cons_func` a **bounded, visible retry with
backoff**, while leaving the existing business-logic-failure behavior
(ack + notify `reply_to`) unchanged:

- On an unhandled exception, if the message has been attempted fewer than
  `MAX_DELIVERY_ATTEMPTS` (3) times, republish it to a new
  `<queue>.retry` queue and ack the original off the main queue. The
  retry queue has `x-message-ttl` (30s) and
  `x-dead-letter-exchange`/`x-dead-letter-routing-key` pointing back at
  the *existing* exchange/routing key, so once the TTL expires RabbitMQ
  automatically redelivers it to the main queue — no polling or scheduler
  needed.
- Once attempts are exhausted, publish to a new `<queue>.failed` queue
  (a durable holding area for manual inspection — no consumer yet) and
  send a failure notification to `reply_to`, same as the existing
  business-failure path.
- A message that fails to even parse as JSON goes straight to
  `<queue>.failed` without burning retry attempts, since retrying
  unparseable bytes can never succeed.
- Attempt count is tracked with an **app-managed header**
  (`x-veribroke-attempt`), not RabbitMQ's native `x-death`. Using
  `x-death` would require setting `x-dead-letter-exchange` directly on
  the *main* queue (`veribroke.mpesa-stk`) — but that queue already
  exists in production without that argument, and RabbitMQ raises
  `PRECONDITION_FAILED (406)` on redeclare with different arguments,
  which would crash the consumer at startup against the real broker.
  Routing everything through brand-new `.retry`/
  `.failed` queues means the main queue's `queue_declare` call stays
  byte-for-byte identical to today, so this ships with zero required
  operational/migration step.
- `print()` calls in this file were replaced with `logging` (module
  logger `rabbit.consumers`) as a low-cost side effect of touching this
  code; log formatting/handlers/correlation IDs are still tracked
  separately as the broader observability phase.

Verified two ways:
- Unit tests (`rabbit/tests.py`, mocked channel) covering: success path
  unchanged, business-failure path unchanged, exception-with-attempts-
  remaining requeues to `.retry`, exception-at-max-attempts goes to
  `.failed` + notifies, malformed JSON skips straight to `.failed`.
- A one-off smoke test against a real local RabbitMQ broker: (a)
  pre-declared a queue with today's exact (bare) arguments to simulate
  "already exists in production", then ran `ConsumerListener` against it
  and confirmed no `PRECONDITION_FAILED`; (b) published a message that
  fails once, confirmed it round-trips through `.retry` and is
  redelivered to the main queue and succeeds. Not part of the committed
  suite (needs a live broker) but confirms the broker-level behavior
  mocks can't.

## Consequences

- Transient failures (DB blips, Daraja hiccups, unexpected exceptions)
  now get up to 3 attempts with a 30s backoff instead of either being
  silently discarded or livelocking the consumer thread forever.
- Poison messages (a deterministic bug that fails every time) are bounded
  to 3 attempts and land in a `.failed` queue for manual triage, instead
  of retrying forever and blocking every other message behind them
  (`prefetch_count=1`).
- No production RabbitMQ topology migration/downtime is required — the
  main queue's declared arguments are untouched; only new queues are
  added.
- New operational surface: `<queue>.failed` queues now exist and will
  silently accumulate messages with no consumer or alerting yet. This is
  a known, deliberate gap — building alerting/consumption for it is
  tracked as follow-up work, not bundled into this change.
- Retrying does **not** add idempotency protection. For the split-
  transaction path (`trans` saved before the Daraja call, see ADR 0001),
  a retry after a crash mid-flow could plausibly send a second real STK
  push if the first one actually reached Safaricom before the crash. For
  the non-split path, no row is persisted until after Daraja responds,
  so there's nothing yet to check against. Closing this fully needs a
  proper idempotency guard (check for an existing `Transactions` row
  before calling Daraja) and extending early persistence to the non-split
  path — tracked as separate follow-up work, deliberately not bundled
  into this change to keep it reviewable.
- Retry/backoff parameters (`MAX_DELIVERY_ATTEMPTS`, `RETRY_TTL_MS`) are
  fixed constants, not env-configurable. Simpler and zero new required
  deploy config; can become configurable later if operational experience
  calls for it.