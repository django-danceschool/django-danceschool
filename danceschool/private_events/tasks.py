from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from huey import crontab
from huey.contrib.djhuey import db_task, db_periodic_task
import logging

from danceschool.core.constants import getConstant
from .models import EventReminder


# Define logger for this file
logger = logging.getLogger(__name__)


@db_task(retries=3)
def sendReminderEmail(reminder_pk):
    '''
    Send reminder emails for a single EventReminder instance.
    Called by scheduleTask() at the right time, and also by the periodic
    fallback to catch anything missed due to downtime.
    '''

    if not getConstant('general__enableCronTasks'):
        return

    try:
        reminder = EventReminder.objects.get(pk=reminder_pk)
    except EventReminder.DoesNotExist:
        logger.warning('sendReminderEmail: reminder %s not found, skipping.', reminder_pk)
        return

    if reminder.completed:
        logger.debug('sendReminderEmail: reminder %s already completed, skipping.', reminder_pk)
        return

    for user in reminder.notifyList.all():
        sent = sendReminderEmailToUser(user, reminder)
        if sent:
            logger.info(
                'Email notification sent to user: %s %s at %s',
                user.first_name, user.last_name, user.email
            )
        else:
            logger.warning(
                'Unable to send email to user: %s %s at %s',
                user.first_name, user.last_name, user.email
            )

    EventReminder.objects.filter(pk=reminder_pk).update(completed=True, scheduledTaskId=None)


@db_periodic_task(crontab(hour='*/3', minute='0'))
def sendReminderEmails():
    '''
    Fallback safety net: every 3 hours, find any due reminders that were not
    sent by their scheduled single-reminder tasks (e.g. after a server restart)
    and enqueue them.
    '''

    if not getConstant('general__enableCronTasks'):
        return

    due_reminders = EventReminder.objects.filter(
        time__lte=timezone.now(),
        completed=False,
        notifyList__isnull=False,
    ).distinct()

    if not due_reminders.exists():
        logger.debug('Reminder fallback: no due reminders found.')
        return

    for reminder in due_reminders:
        logger.info('Reminder fallback: enqueuing sendReminderEmail for reminder %s.', reminder.pk)
        sendReminderEmail(reminder.pk)


def sendReminderEmailToUser(user, reminder):
    subject = _('REMINDER: ') + reminder.eventOccurrence.event.name
    subject += ' on ' + reminder.eventOccurrence.startTime.strftime('%A, %B %-d, %Y')
    if not reminder.eventOccurrence.allDay:
        subject += ' at ' + reminder.eventOccurrence.startTime.strftime('%-I:%M %p')

    content = render_to_string('private_events/reminder_emails.html', {
        'name': ' '.join([user.first_name, user.last_name]),
        'event': reminder.eventOccurrence.event,
        'occurrence': reminder.eventOccurrence,
        'businessName': getConstant('contact__businessName'),
    })

    try:
        if getConstant('email__disableSiteEmails') and getConstant('email__enableErrorEmails'):
            sent = send_mail(
                subject, content,
                getConstant('email__defaultEmailFrom'),
                [
                    getConstant('email__errorEmailTo'),
                ],
                fail_silently=False)
        else:
            sent = send_mail(
                subject, content,
                getConstant('email__defaultEmailFrom'),
                [
                    user.email,
                ],
                fail_silently=False)
    except Exception as e:
        logger.error('Error in sending reminder emails: %s' % e)
        return False
    if sent:
        return True
    return False
