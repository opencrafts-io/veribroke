import time
from payments.mpesa import MpesaHandler


def make_mpesa_stk(body):
        amount = body.get("amount")
        phone_number = body.get("phone_number")

        if not amount or not phone_number:
            return "Missing required fields"
        
        # creating mpesa object to handle transactions
        mpesa_client = MpesaHandler()

        mpesa_payload = {
            "amount": amount,
            "phone_number": phone_number,
        }        

        resp_status ,resp_data = mpesa_client.make_stk_push(mpesa_payload)
        if resp_status == 200:
            # await for 60 seconds
            num_retries = 0
            # check until there is a response from Mpesa
            while True:
                # TODO await all sleep and requests to the outside
                time.sleep(1)
                # was successful query for status
                trans_status, trans_resp = mpesa_client.query_transaction_status(
                    resp_data['CheckoutRequestID'],
                )
                if trans_resp['ResultDesc'] == 'The transaction is still under processing':
                    continue
                if trans_status == 200:
                    break
                num_retries += 1
                # avoid retrying forever
                if num_retries >= 90:
                    break
            # was successful querying
            if trans_status == 200:
                
                if trans_resp['ResultCode'] == '0':
                    return "Payment Received Successfully"
                else:
                    # transaction was not successful
                    return "transaction was not successfully"
            else:
                return "Ooops Something Happened!Try Again Later"
        else:
            return resp_data['errorMessage']