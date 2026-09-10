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
(ack + notify `reply_to`) unchanged, using RabbitMQ's native
dead-lettering rather than reinventing it in application code:

- The main queue (`veribroke.mpesa-stk`) now declares
  `x-dead-letter-exchange`/`x-dead-letter-routing-key` pointing at a new
  `<queue>.retry` binding on the *existing* exchange. On an unhandled
  exception, if the message has been attempted fewer than
  `MAX_DELIVERY_ATTEMPTS` (3) times (per RabbitMQ's own `x-death` header
  count), the consumer just calls `channel.basic_nack(requeue=False)` —
  RabbitMQ handles moving it to the retry queue itself, no manual
  republish or attempt-tracking header needed.
- The retry queue has `x-message-ttl` (30s) and its own
  `x-dead-letter-exchange`/`x-dead-letter-routing-key` pointing back at
  the main exchange/routing key, so once the TTL expires RabbitMQ
  automatically redelivers the message to the main queue for another
  attempt — a passive delay buffer, no consumer attached.
- Once attempts are exhausted, publish to a new `<queue>.failed` queue
  (a durable holding area for manual inspection — no consumer yet) and
  send a failure notification to `reply_to`, same as the existing
  business-failure path. This is the one routing decision RabbitMQ's
  static per-queue DLX config can't express conditionally, so it's the
  only case that still needs a manual `basic_publish`.
- A message that fails to even parse as JSON goes straight to
  `<queue>.failed` without burning retry attempts (via the same manual
  publish path), since retrying unparseable bytes can never succeed and
  routing it through nack would just cycle it forever.
- `print()` calls in this file were replaced with `logging` (module
  logger `rabbit.consumers`) as a low-cost side effect of touching this
  code; log formatting/handlers/correlation IDs are still tracked
  separately as the broader observability phase.

This does require changing `veribroke.mpesa-stk`'s declared queue
arguments, and that queue already exists in production without them —
RabbitMQ raises `PRECONDITION_FAILED (406)` on redeclare with different
arguments (confirmed against a real broker, see below), so **this
requires an operational step**: the queue (or its exchange) must be
deleted before this ships, so it gets recreated with the new arguments
on first connect. Explicitly accepted as reasonable operational cost in
exchange for not hand-rolling retry/attempt-tracking logic that
RabbitMQ already provides natively.

Verified two ways:
- Unit tests (`rabbit/tests.py`, mocked channel) covering: success path
  unchanged, business-failure path unchanged, exception-with-attempts-
  remaining nacks (not published) to trigger the DLX, exception-at-
  max-attempts publishes to `.failed` + notifies, malformed JSON skips
  straight to `.failed`.
- A scripted run against a real local RabbitMQ broker: (a) pre-declared
  the queue with today's exact (bare) arguments to simulate "already
  exists in production"; (b) confirmed redeclaring it with the new DLX
  arguments does raise `PRECONDITION_FAILED`, validating the operational
  step above is real; (c) deleted and let `ConsumerListener` recreate it,
  then published a message that fails once and confirmed it round-trips
  through nack → DLX → `.retry` → TTL → redelivery → success on the main
  queue. Not part of the committed suite (needs a live broker) but
  confirms the broker-level behavior mocks can't.

## Consequences

- Transient failures (DB blips, Daraja hiccups, unexpected exceptions)
  now get up to 3 attempts with a 30s backoff instead of either being
  silently discarded or livelocking the consumer thread forever.
- Poison messages (a deterministic bug that fails every time) are bounded
  to 3 attempts and land in a `.failed` queue for manual triage, instead
  of retrying forever and blocking every other message behind them
  (`prefetch_count=1`).
- **Requires a production deploy step**: the `veribroke.mpesa-stk` queue
  (or its exchange) must be deleted before/during this deploy so it gets
  recreated with the new `x-dead-letter-*` arguments — deploying the code
  without doing so will crash the consumer with `PRECONDITION_FAILED` on
  startup. Deliberately accepted in exchange for simpler code (native
  `x-death` counting instead of an app-managed header, one nack instead
  of a manual publish for the common retry case).
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