from decimal import Decimal
from django.db import transaction
from payments.models import SplitTransactions
from payments.models import Transactions
from payments.stkpush_mpesa.mpesa import MpesaHandler
from rabbit.rabbit_setup import RabbitSetup
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from veribroke import settings

import json


class TestAPIView(APIView):
    def post(self, request, *args, **kwargs):
        """
        Docstring for post
        
        :param self: Description
        :param request: Description
        :param args: Description
        :param kwargs: Description
        """
        print(request.body)
        return Response(
            {"message": "Success got it"},
            status=status.HTTP_200_OK
        )


class StkPushCallBack(APIView):
    def post(self, request, *args, **kwargs):
        """
        will be receive notifications from safaricom for a certain callback
        """
        print("recieved mpesa call back")
        print(request.data)
        checkout_id = request.data["Body"]["stkCallback"]["CheckoutRequestID"]
        result_code = request.data["Body"]["stkCallback"]["ResultCode"]
        result_desc = request.data["Body"]["stkCallback"]["ResultDesc"]

        with transaction.atomic():
            trans = Transactions.objects.filter(reference_id=checkout_id).first()
            if not trans:
                # TODO how to handle this
                # received callback for transaction not recorded in db, log this
                return Response(
                    {"message": "transaction not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            trans.message = result_desc

            if result_code == 0:
                # was success
                trans.status = "success"
                trans.trans_code = request.data["Body"]["stkCallback"]\
                    ["CallbackMetadata"]["Item"][1]["Value"]
            else:
                trans.status = "failure"
            
            trans.save()

            if trans.split and result_code == 0:
                split_trans = SplitTransactions.objects.get(
                    split_id=trans.request_id,
                )
                mpesa_client = MpesaHandler()
                split_trans_type = split_trans.trans_type
                resp_code, resp_data = None, None
                if split_trans_type == "pochi":
                    resp_code, resp_data = mpesa_client.send_to_user(
                        is_pochi=True,
                        amount=split_trans.trans_amount,
                        recipient=split_trans.recipient,
                        remarks=trans.trans_desc,
                        occasion=split_trans.occassion,
                    )
                elif split_trans_type == "personal":
                    resp_code, resp_data = mpesa_client.send_to_user(
                        is_pochi=False,
                        amount=split_trans.trans_amount,
                        recipient=split_trans.recipient,
                        remarks=trans.trans_desc,
                        occasion=split_trans.occassion
                    )
                elif split_trans_type == "paybill":
                    resp_code, resp_data = mpesa_client.send_to_business(
                        is_paybill=True,
                        amount=split_trans.trans_amount,
                        recipient=split_trans.recipient,
                        remarks=trans.trans_desc,
                        account_reference=split_trans.account_reference,
                        requester=split_trans.recipient,
                    )
                elif split_trans_type == "till":
                    resp_code, resp_data = mpesa_client.send_to_business(
                        is_paybill=False,
                        amount=split_trans.trans_amount,
                        recipient=split_trans.recipient,
                        remarks=trans.trans_desc,
                        account_reference=split_trans.account_reference,
                        requester=split_trans.recipient,
                    )
                # print(resp_code, resp_data)
                if resp_code == 200 and str(resp_data["ResponseCode"]) == "0":
                    split_trans.status = "processed"
                    split_trans.reference_id = resp_data["OriginatorConversationID"]
                else:
                    split_trans.status = "failedprocessing"
                    if resp_data.get("errorMessage"):
                        split_trans.message = resp_data.get("errorMessage")
                    elif resp_data.get("ResponseDescription"):
                        split_trans.message = resp_data.get("ResponseDescription")
                
                split_trans.save()
        
        rabbit = RabbitSetup()

        rabbit.publish_message(
            exchange=settings.env("RABBITMQ_NOTIFICATION_EXCHANGE"),
            routing_key=trans.reply_to,
            body=json.dumps({
                "request_id": trans.request_id,
                "success": result_code == 0,
                "message": result_desc,
                "errors": None,
                "metadata": request.data
            },),
            persist=True
        )
        
        rabbit.close()
        
        return Response(
            {"message": "received successfully"},
            status=status.HTTP_200_OK,
        )


class SplitTransCallBack(APIView):
    """
    will receive notifications from safaricom for callbacks for split transactions
    """
    def post(self, request, *args, **kwargs):
        """
        receive notifications from safaricom for callbacks for split transactions
        """
        identification = request.data["Result"]["OriginatorConversationID"]
        result_code = request.data["Result"]["ResultCode"]
        result_desc = request.data["Result"]["ResultDesc"]
        transaction_code = request.data["Result"]["TransactionID"]

        split_trans = SplitTransactions.objects.filter(
            reference_id=identification,
        ).first()

        if not split_trans:
            # TODO how to handle this
            # received callback for transaction not recorded in db, log this
            return Response(
                {"message": "transaction not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        split_trans.trans_code = transaction_code
        split_trans.message = result_desc

        if result_code == 0:
            split_trans.status = "success"
            trans_fee = 0

            for result in request.data["Result"]["ResultParameters"]\
                ["ResultParameter"]:
                if result["Key"] == "DebitPartyCharges":
                    trans_fee = Decimal(result["Value"])
                    break
                
            split_trans.trans_fee = trans_fee
        else:
            split_trans.status = "failure"
        
        split_trans.save()
        
        return Response(
            {"message": "received successfully"},
            status=status.HTTP_200_OK,
        )        