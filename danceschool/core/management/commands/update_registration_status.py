from django.core.management.base import BaseCommand

from danceschool.core.models import Series


class Command(BaseCommand):
    help = 'Update the registration status for series and events that should be opened/closed based on the current time'

    def handle(self, *args, **options):
        self.stdout.write('Checking and updating registration status of all opened class series.')

        open_series = Series.objects.filter(**{'registrationOpen': True})

        for series in open_series:
            series.updateRegistrationStatus()
        self.stdout.write('done.')
