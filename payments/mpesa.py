import time
import math
import base64
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth
from veribroke import settings


class MpesaHandler:
    now = None
    shortcode = None
    consumer_key = None
    consumer_secret = None
    access_token_url = None
    access_token = None
    access_token_expiration = None
    stk_push_url = None
    my_callback_url = None
    query_status_url = None
    timestamp = None
    passkey = None

    def __init__(self):
        self.now = datetime.now()
        
        self.shortcode = settings.env("SAF_SHORTCODE")
        self.consumer_key = settings.env("SAF_CONSUMER_KEY")
        self.consumer_secret = settings.env("SAF_CONSUMER_SECRET")
        self.access_token_url = settings.env("SAF_ACCESS_TOKEN_API")
        self.passkey = settings.env("SAF_PASS_KEY")
        self.stk_push_url = settings.env("SAF_STK_PUSH_API")
        self.query_status_url = settings.env("SAF_STK_PUSH_QUERY_API")
        self.my_callback_url = settings.env("CALLBACK_URL")
        self.password = self.generate_password()

        try:
            self.access_token = self.get_mpesa_access_token()
            if self.access_token is None:
                raise Exception("Request for access token failed")
            else:
                self.access_token_expiration = time.time() + 3599

        except Exception as e:
            # TODO log this error
            print(str(e))

    def get_mpesa_access_token(self):
        try:
            # initializing token to none
            token = None
            res = requests.get(
                self.access_token_url,
                auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret),
            )
            
            token = res.json()['access_token']

            self.headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        except Exception as e:
            print(str(e), "error getting access token")
            raise e

        return token

    def generate_password(self):
        self.timestamp = self.now.strftime("%Y%m%d%H%M%S")
        password_str = self.shortcode + self.passkey + self.timestamp
        password_bytes = password_str.encode()

        return base64.b64encode(password_bytes).decode("utf-8")

    def make_stk_push(self, payload):
        amount = payload['amount']
        phone_number = payload['phone_number']

        push_data = {
            "BusinessShortCode": self.shortcode,
            "Password": self.password,
            "Timestamp": self.timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": math.ceil(float(amount)),
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.my_callback_url,
            "AccountReference": "OPEN CRAFTS",
            # TODO make this dynamic
            "TransactionDesc": "Client Deposit",
        }

        response = requests.post(
            self.stk_push_url,
            json=push_data,
            headers=self.headers
        )

        response_data = response.json()

        return response.status_code, response_data

    def query_transaction_status(self, checkout_request_id):
        query_data = {
            "BusinessShortCode": self.shortcode,
            "Password": self.password,
            "Timestamp": self.timestamp,
            "CheckoutRequestID": checkout_request_id
        }

        response = requests.post(
            self.query_status_url,
            json=query_data,
            headers=self.headers
        )
        
        response_data = response.json()
        
        return response.status_code, response_data