from django.dispatch import receiver

import logging

from danceschool.core.signals import get_additional_event_names
from .helpers import getList


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(get_additional_event_names)
def addEventGuests(sender, event, **kwargs):
    '''
    Add event guests that may be checked in.
    '''
    logger.debug('Signal to add additional event names handled by guestlist app.')

    return getList(event=event, includeRegistrants=False)
