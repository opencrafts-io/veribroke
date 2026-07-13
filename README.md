# Veribroke

Veribroke is the payment gateway for the OpenCrafts ecosystem. It's the
single place that talks to Safaricom's Daraja API on behalf of every
other OpenCrafts service, so no other service has to.

## What it does

Other services publish a payment request (currently M-Pesa STK Push) to
a shared RabbitMQ exchange. Veribroke picks it up, initiates the
transaction with Safaricom, tracks its state through to a final
success/failure callback, and publishes a notification back to whichever
service asked for it. Split transactions — routing part of a payment to
a third party (paybill, till, pochi, or a personal number) — are handled
the same way, as an extension of the same request.

## Why it exists

Payment processing has a lot of failure modes that have nothing to do
with any individual product's business logic: OAuth token handling,
callback verification, retrying transient upstream failures without
double-charging anyone, split-transaction bookkeeping, reconciling
transaction state against what Safaricom actually did. Centralizing that
in one service means:

- **Every other service is decoupled from Safaricom's API directly.**
  If Daraja's contract changes, or a new payment method is added, that's
  a Veribroke change, not an N-service change.
- **Reliability work happens once.** Retry/backoff behavior, dead-letter
  handling, timeouts, and observability for payment flows are built and
  hardened in one place instead of being reimplemented (or skipped)
  per service.
- **Services stay loosely coupled.** Integration happens entirely over
  RabbitMQ — publish a request, get a notification back on your own
  queue. No service needs direct access to another's database or
  synchronous HTTP dependency on Veribroke to get its payment result.

This is money-moving infrastructure for the ecosystem, so it's held to a
correspondingly higher reliability bar than a typical internal service —
see `docs/adrs/` for the engineering decisions behind that, and
`docs/incidents/` for the incident history that's shaped them.

## Integrating with Veribroke

The full protocol reference — exchanges, queues, message schema,
notification handling, and split transactions — lives in
[`docs/mpesa-integration-guide.md`](docs/mpesa-integration-guide.md).
Start there if you're wiring a service up to Veribroke.
