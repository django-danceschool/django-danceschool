from django.conf import settings
from django.utils import timezone
from django.core.management import call_command

from huey import crontab
from huey.contrib.djhuey import db_periodic_task
import logging
from os.path import isdir
from dateutil.relativedelta import relativedelta

from danceschool.core.constants import getConstant


# Define logger for this file
logger = logging.getLogger(__name__)


@db_periodic_task(crontab(hour='*', minute='0'))
def backupDatabase():
    '''
    This task runs every hour in crontab, but it revokes itself in order to have customizable
    frequency in site settings.
    '''

    call_command('backup_now')

    # Revoke until 15 minutes before the next scheduled run.
    frequency = getConstant('backups__backupFrequency')
    replace_to = {
        'hour': int(getConstant('backups__backupHour')),
    }
    relative_to = {'minutes': -15}

    if frequency == 'Monthly':
        this_day = timezone.now().day
        replace_to['day'] = int(getConstant('backups__backupMonthDay'))
        if timezone.now().replace(day=replace_to['day'], hour=replace_to['hour']) < timezone.now():
            relative_to['months'] = 1
    elif frequency == 'Weekly':
        this_weekday = timezone.now().weekday()
        replace_to['weekday'] = int(getConstant('backups__backupWeekday'))
        relative_to['days'] = replace_to['weekday'] - this_weekday

        if (
            relative_to['days'] < 0 or (
                relative_to['days'] == 0 and timezone.now().hour >= replace_to['hour']
            )
        ):
            relative_to['weeks'] = 1
    elif frequency == 'Daily':
        if timezone.now().hour >= replace_to['hour']:
            relative_to['days'] = 1
    else:
        relative_to['hours'] = 1

    nextTime = timezone.now().replace(**replace_to) + relativedelta(**relative_to)
    backupDatabase.revoke(revoke_until=nextTime)

    logger.debug(
        'Next backup will occur at approximately %s.' % (
            (nextTime + relativedelta(minutes=15)).strftime('%Y-%m-%d %H:00:00'),
        )
    )
