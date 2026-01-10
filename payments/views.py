from payments.models import Transactions
from rabbit.rabbit_setup import RabbitSetup
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from veribroke import settings

import json


class TestAPIView(APIView):
    def get(self, request, *args, **kwargs):
        """
        Docstring for post
        
        :param self: Description
        :param request: Description
        :param args: Description
        :param kwargs: Description
        """
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
        # getting transaction
        checkout_id = request.data["Body"]["stkCallback"]["CheckoutRequestID"]
        result_code = request.data["Body"]["stkCallback"]["ResultCode"]
        result_desc = request.data["Body"]["stkCallback"]["ResultDesc"]

        transaction = Transactions.objects.filter(reference_id=checkout_id).first()
        if not transaction:
            # TODO how to handle this
            # received callback for transaction not recorded in db, log this
            return Response(
                {"message": "trans not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        transaction.message = result_desc

        if result_code == 0:
            # was success
            transaction.status = "success"
            transaction.trans_code = request.data["Body"]["stkCallback"]\
                ["CallbackMetadata"]["Item"][1]["Value"]
        else:
            transaction.status = "failure"
        
        transaction.save()
        
        rabbit = RabbitSetup()

        rabbit.publish_message(
            exchange=settings.env("RABBITMQ_NOTIFICATION_EXCHANGE"),
            routing_key=transaction.reply_to,
            body=json.dumps({
                "request_id": transaction.request_id,
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