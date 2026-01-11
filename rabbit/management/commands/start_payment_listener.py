from veribroke.settings import env
from django.core.management.base import BaseCommand
from payments.stkpush_mpesa.utils import make_mpesa_stk
from rabbit.consumers import ConsumerListener
from rabbit.rabbit_setup import RabbitSetup


class Command(BaseCommand):
    help = "Start all registered RabbitMQ consumers"

    def handle(self, *args, **options):
       # setup rabbit
       rabbit = RabbitSetup()
       rabbit.declare_default_exchanges()

       # declaring queue to listen for stk pushes
       ConsumerListener(
           channel=rabbit.channel,
           exchange= env("RABBITMQ_EXCHANGE"),
           queue_name="veribroke.mpesa-stk",
           routing_key="veribroke.mpesa-stk",
           cons_func=make_mpesa_stk,
           notifies=True,
       )

       for consumer in ConsumerListener.Consumers.values():
           consumer.start()
       
       print("wiiih")
        
 