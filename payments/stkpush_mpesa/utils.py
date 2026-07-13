from django.db import transaction
from django.utils import timezone
from payments.models import SplitTransactions
from payments.models import Transactions
from payments.stkpush_mpesa.mpesa import MpesaHandler
from payments.stkpush_mpesa.serializers import SplitTransactionSerializer
from payments.stkpush_mpesa.serializers import StkPushSerializers

import logging

logger = logging.getLogger(__name__)


def make_mpesa_stk(body):
        """
        Sends Mpesa stk to Daraja

        :param body: a dict having the body, containing values necessary
            for a transaction
        """
        serializer = StkPushSerializers(data=body)

        if not serializer.is_valid():
            logger.warning(
                "stk push request failed validation",
                extra={"errors": serializer.errors},
            )
            return False, "transaction was not successful", serializer.errors, {}
        
        with transaction.atomic():
            trans = Transactions()
            trans.request_id = serializer.validated_data['request_id']
            trans.target_user_id = serializer.validated_data.get('target_user_id')
            trans.trans_amount = serializer.validated_data['trans_amount']
            trans.sender = serializer.validated_data['phone_number']
            trans.trans_type = "MPESASTKPUSH"
            trans.service_name = serializer.validated_data['service_name']
            trans.reply_to = serializer.validated_data['reply_to']
            trans.trans_desc = serializer.validated_data['trans_desc']
            trans.created = timezone.now()

            split_data = body.get("split_data")

            if split_data:
                split_serializer = SplitTransactionSerializer(data=split_data)
                if not split_serializer.is_valid():
                    logger.warning(
                        "split transaction request failed validation",
                        extra={
                            "request_id": trans.request_id,
                            "errors": split_serializer.errors,
                        },
                    )
                    return False, "transaction was not successful",\
                        split_serializer.errors, {}

                split_trans_type = split_serializer.validated_data["extras"]["type"]

                if split_trans_type not in [
                        "till",
                        "pochi",
                        "paybill",
                        "personal",
                    ]:
                    logger.warning(
                        "invalid mpesa stk split type",
                        extra={
                            "request_id": trans.request_id,
                            "split_trans_type": split_trans_type,
                        },
                    )
                    return False, "invalid type for mpesa stk split",\
                        split_serializer.errors, {}

                account_reference = split_data["extras"].get("account_reference")

                if split_trans_type == "paybill" and not account_reference :
                    logger.warning(
                        "missing account reference for paybill split",
                        extra={"request_id": trans.request_id},
                    )
                    return False, "missing account reference for paybill",\
                        None, {}

                trans.split = True

                if not account_reference:
                    account_reference = serializer.validated_data['request_id']

                # split_trans.split_id is a non-deferrable FK to trans, so
                # trans must already exist in the DB before this insert.
                # reference_id stays null until the STK push responds.
                trans.save()

                split_trans = SplitTransactions(
                    originator="MPESASTKPUSH",
                    split_id=trans,
                    trans_amount=split_serializer.validated_data["extras"]\
                        ["amount"],
                    trans_type=split_serializer.validated_data["extras"]["type"],
                    recipient=split_serializer.validated_data["extras"]\
                        ["recipient"],
                    account_reference=account_reference, 
                    occassion=split_serializer.validated_data["extras"]\
                        ["occassion"],
                )

                try:
                    split_trans.save()
                except Exception as e:
                    logger.exception(
                        "failed to persist split transaction",
                        extra={"request_id": trans.request_id},
                    )
                    return False, "transaction was not successful", str(e), {}

            # creating mpesa object to handle transactions
            mpesa_client = MpesaHandler()

            mpesa_payload = {
                "amount": serializer.validated_data['trans_amount'],
                "phone_number": serializer.validated_data['phone_number'],
                "account_reference": serializer.validated_data['request_id'],
            }

            logger.info(
                "initiating mpesa stk push",
                extra={"request_id": trans.request_id, "split": trans.split},
            )

            resp_status ,resp_data = mpesa_client.make_stk_push(mpesa_payload)
            if resp_status == 200:
                try:
                    trans.reference_id = resp_data['CheckoutRequestID']
                    trans.save()
                except Exception as e:
                    logger.exception(
                        "stk push succeeded but failed to persist the transaction",
                        extra={
                            "request_id": trans.request_id,
                            "checkout_request_id": resp_data.get('CheckoutRequestID'),
                        },
                    )
                    return False, "Stk Sent But An Error Occured", str(e), resp_data

                logger.info(
                    "stk push succeeded",
                    extra={
                        "request_id": trans.request_id,
                        "checkout_request_id": resp_data.get('CheckoutRequestID'),
                    },
                )
                return True, "Stk Sent Successfully", None, resp_data
            else:
                logger.warning(
                    "stk push failed",
                    extra={
                        "request_id": trans.request_id,
                        "resp_status": resp_status,
                        "error_message": resp_data.get('errorMessage'),
                    },
                )

                if trans.split:
                    # trans/split_trans were already persisted (pending)
                    # to satisfy the FK above; don't leave them dangling.
                    trans.status = "failure"
                    trans.message = resp_data.get('errorMessage')
                    trans.save()

                    split_trans.status = "failedprocessing"
                    split_trans.message = resp_data.get('errorMessage')
                    split_trans.save()

                return False, "Couldn't send stk push", resp_data['errorMessage'], resp_data