# 4. Normalize phone numbers to Daraja's canonical format instead of passing them through unchanged

Date: 2026-07-13

## Status

accepted

## Context

Discovered while manually testing the STK push flow end-to-end
(publishing a real request for `+254110877322`): no prompt arrived, no
`Transactions` row existed for the request (the known non-split-failure
gap from ADR 0001), and the RabbitMQ queue showed the message had been
consumed with no retry/failure -- so it wasn't a broker or environment
problem, the request had reached Safaricom and been rejected there.

Calling `MpesaHandler.make_stk_push` directly against the live Daraja
API confirmed it: `phone_number="+254110877322"` gets `400 Bad Request -
Invalid PhoneNumber`; the exact same request with `phone_number=
"254110877322"` (no `+`) gets `200`, `ResponseCode: 0`, and the prompt
is delivered.

`StkPushSerializers.validate_phone_number` accepts four input shapes via
regex (`+254...`, `254...`, `0...`, bare `7.../1...`) but only validates
the shape -- it returns the caller's original string unchanged. Whatever
format the caller sent flows straight through to Daraja's `PartyA`/
`PhoneNumber` fields, which only accept the canonical `254XXXXXXXXX`
form. In practice this means any client sending E.164-style numbers
(`+254...`, one of the most common phone number storage formats) has
been failing on essentially every request -- rejected by Safaricom, not
by Veribroke, so nothing about it was visible from Veribroke's side
beyond a failure notification carrying Safaricom's raw error string.

## Decision

Normalize inside `validate_phone_number` itself, at the point the shape
is already being parsed: return `f"254{match.group(1)}"` instead of the
original `value`. All four previously-accepted input shapes continue to
validate exactly as before -- this only changes what
`validated_data['phone_number']` *contains* once validation passes, not
what's accepted at the wire level. No contract change for callers: a
service already sending `254XXXXXXXXX` sees no difference; a service
sending `+254XXXXXXXXX`, `0XXXXXXXXX`, or bare `XXXXXXXXX` now actually
gets a working STK push instead of a silent-from-Veribroke's-side
rejection.

`serializer.validated_data['phone_number']` feeds both
`trans.sender` and the Daraja request payload
(`payments/stkpush_mpesa/utils.py`), so fixing it at the validation
boundary covers both call sites with one change -- no edits needed in
`mpesa.py` or `utils.py` itself.

Verified against the exact failure this uncovered: new tests in
`payments/tests.py` (`PhoneNumberNormalizationTests`) cover all four
input shapes normalizing to `254110877322`, plus an end-to-end
`make_mpesa_stk` test confirming the normalized number is what actually
gets sent to `MpesaHandler.make_stk_push` and stored on `trans.sender`.
Full suite (17 tests), `manage.py check`, and `makemigrations --check`
all pass. No migration needed -- this is a pure validation-layer change.

## Consequences

- Any existing client sending `+254`, `0`-prefixed, or bare local-format
  phone numbers gets a working STK push instead of a rejection from
  Safaricom on every request. This was likely a live, widespread bug,
  not a theoretical one -- caught by manually testing the flow with a
  real E.164-formatted number.
- `Transactions.sender` will now consistently store the canonical
  `254XXXXXXXXX` form for all new rows, regardless of how the caller
  formatted it. Historical rows are left as-is (whatever raw format was
  originally sent) -- no backfill, consistent with treating past data as
  a frozen audit trail rather than something to retroactively rewrite.
- Not addressed here (explicitly out of scope, tracked as a follow-up):
  `ExtrasSerializer.recipient` (the split-transaction disbursement
  target for `pochi`/`personal`/`paybill`/`till`) has **no** format
  validation or normalization at all today, and flows into
  `send_to_user`/`send_to_business`'s `PartyB` field the same
  unvalidated way `phone_number` used to. It likely has the same class
  of bug for phone-number-shaped recipients. Left alone here to keep
  this change scoped to the exact failure just reproduced and verified
  against the live API.
- The still-open gap from ADR 0001 (non-split STK failures persist no
  `Transactions` row) is what made this bug invisible from Veribroke's
  own data -- the only reason it surfaced here is a direct, synchronous
  call against the live API during manual testing. That gap remains
  open and would make a similar issue hard to spot from Veribroke's
  side alone in the future.