from django.core.management.base import BaseCommand

from danceschool.financial.helpers import createExpenseItemsForEvents, createExpenseItemsForVenueRental,createRevenueItemsForRegistrations
from danceschool.core.constants import getConstant


class Command(BaseCommand):
    help = 'Create expense items for recurring expenses and generate revenue items for registrations'

    def handle(self, *args, **options):
        if getConstant('financial__autoGenerateExpensesEventStaff'):
            self.stdout.write('Generating expense items for event staff...')
            createExpenseItemsForEvents()
            self.stdout.write('...done.')
        else:
            self.stdout.write('Generation of expense items for event staff is not enabled.')

        if getConstant('financial__autoGenerateExpensesVenueRental'):
            self.stdout.write('Generating expense items for venue rentals...')
            createExpenseItemsForVenueRental()
            self.stdout.write('...done.')
        else:
            self.stdout.write('Generation of expense items for venue rental is not enabled.')

        if getConstant('financial__autoGenerateRevenueRegistrations'):
            self.stdout.write('Generating revenue items for registrations...')
            createRevenueItemsForRegistrations()
            self.stdout.write('...done.')
        else:
            self.stdout.write('Generation of revnue items for registrations is not enabled.')
