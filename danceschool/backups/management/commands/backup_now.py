from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings
from django.utils import timezone

import logging
import os

from danceschool.core.constants import getConstant

# Define logger for this file
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Perform a backup of the site database, using configuration options from site settings.'

    def handle(self, *args, **options):
        backup_folder = getattr(settings, 'BACKUP_LOCATION', '/backup')
        if not os.path.isdir(backup_folder):
            logger.error(
                'Backup failed because destination folder does not exist; ' +
                'BACKUP_LOCATION must be updated in project settings.py.'
            )
            return None
        backup_loc = os.path.join(
            backup_folder,
            '%s%s.json' % (
                getConstant('backups__filePrefix'), timezone.now().strftime('%Y%m%d%H%M%S')
            )
        )

        if not getConstant('backups__enableDataBackups'):
            logger.info('Aborting backup because backups are not enabled in global settings.')
            return None

        logger.info('Beginning JSON backup to file %s.' % backup_loc)
        with open(backup_loc, 'w') as f:
            try:
                call_command('dumpdata', indent=1, format='json', natural_foreign=True, stdout=f)
                logger.info('Backup completed.')
            except CommandError:
                logger.error('Backup to file %s failed.' % backup_loc)
