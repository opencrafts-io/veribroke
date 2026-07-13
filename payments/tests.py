from unittest.mock import MagicMock, patch

from django.test import TestCase

from payments.models import SplitTransactions
from payments.models import Transactions
from payments.stkpush_mpesa.serializers import StkPushSerializers
from payments.stkpush_mpesa.utils import make_mpesa_stk


def _split_payload(request_id, **overrides):
    payload = {
        "request_id": request_id,
        "target_user_id": "user-1",
        "trans_amount": "500",
        "trans_desc": "Test payment",
        "service_name": "TESTSVC",
        "reply_to": "test.reply",
        "phone_number": "254712345678",
        "split_data": {
            "originator": "MPESA",
            "extras": {
                "type": "pochi",
                "amount": "200",
                "recipient": "254799999999",
                "occassion": "Commission",
            },
        },
    }
    payload.update(overrides)
    return payload


class MakeMpesaStkSplitTransactionTests(TestCase):
    """
    Regression tests for the FK-ordering bug: SplitTransactions.split_id
    points at a Transactions row that must exist in the DB before the
    child insert, since it's a non-deferrable Postgres FK.
    """

    @patch("payments.stkpush_mpesa.utils.MpesaHandler")
    def test_split_transaction_success_persists_parent_then_child(self, mock_handler_cls):
        mock_handler = MagicMock()
        mock_handler.make_stk_push.return_value = (
            200,
            {"CheckoutRequestID": "ws_CO_1"},
        )
        mock_handler_cls.return_value = mock_handler

        success, message, errors, data = make_mpesa_stk(
            _split_payload("req-split-success")
        )

        self.assertTrue(success, msg=f"expected success, got errors={errors}")

        trans = Transactions.objects.get(pk="req-split-success")
        self.assertTrue(trans.split)
        self.assertEqual(trans.reference_id, "ws_CO_1")

        split_trans = SplitTransactions.objects.get(split_id="req-split-success")
        self.assertEqual(split_trans.recipient, "254799999999")
        self.assertEqual(split_trans.status, "pending")

    @patch("payments.stkpush_mpesa.utils.MpesaHandler")
    def test_split_transaction_stk_failure_marks_failed_not_dangling(self, mock_handler_cls):
        mock_handler = MagicMock()
        mock_handler.make_stk_push.return_value = (
            500,
            {"errorMessage": "upstream unavailable"},
        )
        mock_handler_cls.return_value = mock_handler

        success, message, errors, data = make_mpesa_stk(
            _split_payload("req-split-failure")
        )

        self.assertFalse(success)

        trans = Transactions.objects.get(pk="req-split-failure")
        self.assertEqual(trans.status, "failure")
        self.assertIsNone(trans.reference_id)

        split_trans = SplitTransactions.objects.get(split_id="req-split-failure")
        self.assertEqual(split_trans.status, "failedprocessing")

    @patch("payments.stkpush_mpesa.utils.MpesaHandler")
    def test_second_split_request_not_blocked_by_prior_failed_reference_id(
        self, mock_handler_cls
    ):
        mock_handler = MagicMock()
        mock_handler_cls.return_value = mock_handler

        mock_handler.make_stk_push.return_value = (
            500,
            {"errorMessage": "upstream unavailable"},
        )
        first_success, *_ = make_mpesa_stk(_split_payload("req-split-first"))
        self.assertFalse(first_success)

        mock_handler.make_stk_push.return_value = (
            200,
            {"CheckoutRequestID": "ws_CO_2"},
        )
        second_success, message, errors, data = make_mpesa_stk(
            _split_payload("req-split-second")
        )

        self.assertTrue(second_success, msg=f"expected success, got errors={errors}")
        self.assertEqual(
            Transactions.objects.get(pk="req-split-second").reference_id,
            "ws_CO_2",
        )

    @patch("payments.stkpush_mpesa.utils.MpesaHandler")
    def test_non_split_transaction_still_saves_once_on_success(self, mock_handler_cls):
        mock_handler = MagicMock()
        mock_handler.make_stk_push.return_value = (
            200,
            {"CheckoutRequestID": "ws_CO_3"},
        )
        mock_handler_cls.return_value = mock_handler

        body = _split_payload("req-non-split")
        body.pop("split_data")

        success, message, errors, data = make_mpesa_stk(body)

        self.assertTrue(success, msg=f"expected success, got errors={errors}")
        trans = Transactions.objects.get(pk="req-non-split")
        self.assertFalse(trans.split)
        self.assertEqual(trans.reference_id, "ws_CO_3")
        self.assertFalse(SplitTransactions.objects.filter(split_id="req-non-split").exists())


class MakeMpesaStkTargetUserIdOptionalTests(TestCase):
    """
    target_user_id is never read by Veribroke's own logic -- it's
    caller-owned bookkeeping. It must stay optional so callers outside
    the original Verisafe-based ecosystem aren't forced to supply one,
    while requests that still send it (existing clients) keep working
    unchanged.
    """

    @patch("payments.stkpush_mpesa.utils.MpesaHandler")
    def test_request_without_target_user_id_succeeds(self, mock_handler_cls):
        mock_handler = MagicMock()
        mock_handler.make_stk_push.return_value = (
            200,
            {"CheckoutRequestID": "ws_CO_no_user"},
        )
        mock_handler_cls.return_value = mock_handler

        body = _split_payload("req-no-user-id")
        body.pop("split_data")
        body.pop("target_user_id")

        success, message, errors, data = make_mpesa_stk(body)

        self.assertTrue(success, msg=f"expected success, got errors={errors}")
        trans = Transactions.objects.get(pk="req-no-user-id")
        self.assertIn(trans.target_user_id, (None, ""))

    @patch("payments.stkpush_mpesa.utils.MpesaHandler")
    def test_request_with_target_user_id_still_persists_it(self, mock_handler_cls):
        mock_handler = MagicMock()
        mock_handler.make_stk_push.return_value = (
            200,
            {"CheckoutRequestID": "ws_CO_with_user"},
        )
        mock_handler_cls.return_value = mock_handler

        body = _split_payload("req-with-user-id")
        body.pop("split_data")

        success, message, errors, data = make_mpesa_stk(body)

        self.assertTrue(success, msg=f"expected success, got errors={errors}")
        trans = Transactions.objects.get(pk="req-with-user-id")
        self.assertEqual(trans.target_user_id, "user-1")


class PhoneNumberNormalizationTests(TestCase):
    """
    Daraja only accepts phone numbers as 254XXXXXXXXX (no '+', no
    leading 0). Veribroke's own validation accepted +254/254/0/bare
    formats but passed them through unchanged, so anything other than
    bare 254XXXXXXXXX got silently rejected by Safaricom with no DB
    record (confirmed against the live API: '+254110877322' -> 400
    Invalid PhoneNumber, '254110877322' -> 200 accepted).
    """

    def _validate(self, raw_number):
        serializer = StkPushSerializers(data={
            "request_id": "phone-fmt-test",
            "trans_desc": "test",
            "service_name": "TESTSVC",
            "reply_to": "test.reply",
            "phone_number": raw_number,
            "trans_amount": "1",
        })
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)
        return serializer.validated_data["phone_number"]

    def test_plus_254_prefix_is_normalized(self):
        self.assertEqual(self._validate("+254110877322"), "254110877322")

    def test_254_prefix_is_left_as_canonical(self):
        self.assertEqual(self._validate("254110877322"), "254110877322")

    def test_leading_zero_is_normalized(self):
        self.assertEqual(self._validate("0110877322"), "254110877322")

    def test_bare_local_number_is_normalized(self):
        self.assertEqual(self._validate("110877322"), "254110877322")

    @patch("payments.stkpush_mpesa.utils.MpesaHandler")
    def test_make_mpesa_stk_sends_normalized_number_to_daraja(self, mock_handler_cls):
        mock_handler = MagicMock()
        mock_handler.make_stk_push.return_value = (
            200,
            {"CheckoutRequestID": "ws_CO_normalized"},
        )
        mock_handler_cls.return_value = mock_handler

        body = _split_payload("req-phone-normalized")
        body.pop("split_data")
        body["phone_number"] = "+254110877322"

        success, message, errors, data = make_mpesa_stk(body)

        self.assertTrue(success, msg=f"expected success, got errors={errors}")
        sent_payload = mock_handler.make_stk_push.call_args.args[0]
        self.assertEqual(sent_payload["phone_number"], "254110877322")
        self.assertEqual(
            Transactions.objects.get(pk="req-phone-normalized").sender,
            "254110877322",
        )
