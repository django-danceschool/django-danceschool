from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from datetime import timedelta

from danceschool.core.models import Registration, Invoice
from danceschool.core.constants import getConstant


class Command(BaseCommand):
    help = 'Clear expired preliminary invoice and session data'

    def handle(self, *args, **options):

        if getConstant('registration__deleteExpiredInvoices'):
            self.stdout.write('Clearing expired data.')
            Invoice.objects.filter(
                status=Invoice.PaymentStatus.preliminary,
                expirationDate__lte=timezone.now() - timedelta(minutes=1)
            ).delete()
            call_command('clearsessions')
        else:
            self.stdout.write('Clearing expired data is disabled.  Nothing was deleted.')
