from payments.stkpush_mpesa.mpesa import MpesaHandler
import time


mpesa = MpesaHandler()
code, response = mpesa.send_to_user(amount="10", is_pochi=False, recipient="254796322949", remarks="Good one", occasion="woow")

print(response)
time.sleep(3)
print(mpesa.query_transaction_status(response['OriginatorConversationID']))