from django.core.management.base import BaseCommand
from payments.paymentqueue.paymentlistener import PaymentListener


class Command(BaseCommand):
    help = 'Launches Listener for payments : RaabitMQ'
    
    def handle(self, *args, **options):
        td = PaymentListener()
        td.start()
        self.stdout.write("Started Consumer Thread")