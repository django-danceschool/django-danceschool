from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from datetime import timedelta

from danceschool.core.models import TemporaryRegistration
from danceschool.core.constants import getConstant


class Command(BaseCommand):
    help = 'Clear expired temporary registration and session data'

    def handle(self, *args, **options):

        if getConstant('registration__deleteExpiredTemporaryRegistrations'):
            self.stdout.write('Clearing expired data.')
            TemporaryRegistration.objects.filter(expirationDate__lte=timezone.now() - timedelta(minutes=1)).delete()
            call_command('clearsessions')
        else:
            self.stdout.write('Clearing expired data is disabled.  Nothing was deleted.')
