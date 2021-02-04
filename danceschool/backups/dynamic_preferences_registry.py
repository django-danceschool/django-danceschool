'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import gettext_lazy as _

from calendar import day_name

from dynamic_preferences.types import BooleanPreference, ChoicePreference, StringPreference, Section
from dynamic_preferences.registries import global_preferences_registry


# Generate a backup section in global preferences.
backups = Section('backups', _('Backups'))


@global_preferences_registry.register
class EnableDataBackups(BooleanPreference):
    section = backups
    name = 'enableDataBackups'
    verbose_name = _('Enable Database Backups')
    help_text = _(
        'Check this box to enable periodic local backups of the site database (recommended).'
    )
    default = False


@global_preferences_registry.register
class BackupFrequency(ChoicePreference):
    section = backups
    name = 'backupFrequency'
    choices = [
        ('Hourly', _('Hourly')),
        ('Daily', _('Daily')),
        ('Weekly', _('Weekly')),
        ('Monthly', _('Monthly')),
    ]
    verbose_name = _('Backup Frequency')
    default = 'Daily'


@global_preferences_registry.register
class BackupMonthDay(ChoicePreference):
    section = backups
    name = 'backupMonthDay'
    choices = [(str(x), str(x)) for x in range(1, 29)]
    verbose_name = _('Backup on day of month')
    default = '1'
    help_text = _('Applies only to monthly backups')


@global_preferences_registry.register
class BackupWeekday(ChoicePreference):
    section = backups
    name = 'backupWeekday'
    choices = [(str(x), _(day_name[x])) for x in range(0, 7)]
    verbose_name = _('Backup on day of week')
    default = '0'
    help_text = _('Applies only to weekly backups')


@global_preferences_registry.register
class BackupHour(ChoicePreference):
    section = backups
    name = 'backupHour'
    choices = [(str(x), '%s:00' % x) for x in range(0, 24)]
    verbose_name = _('Backup on hour of the day')
    default = '0'


@global_preferences_registry.register
class BackupFilePrefix(StringPreference):
    section = backups
    name = 'filePrefix'
    verbose_name = _('Backup File Prefix')
    help_text = _('The date and time of the backup will be appended to this prefix')
    default = 'site_backup_'
