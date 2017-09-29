from huey import crontab
from huey.contrib.djhuey import db_periodic_task
import logging

from danceschool.core.constants import getConstant

from .helpers import createExpenseItemsForEvents, createExpenseItemsForVenueRental,createRevenueItemsForRegistrations


# Define logger for this file
logger = logging.getLogger(__name__)


@db_periodic_task(crontab(minute='*/60'))
def updateFinancialItems():
    '''
    Every hour, create any necessary revenue items and expense items for
    activities that need them.
    '''
    if not getConstant('general__enableCronTasks'):
        return

    logger.info('Creating automatically-generated financial items.')

    if getConstant('financial__autoGenerateExpensesEventStaff'):
        createExpenseItemsForEvents()
    if getConstant('financial__autoGenerateExpensesVenueRental'):
        createExpenseItemsForVenueRental()
    if getConstant('financial__autoGenerateRevenueRegistrations'):
        createRevenueItemsForRegistrations()
