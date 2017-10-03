from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from huey import crontab
from huey.contrib.djhuey import db_periodic_task
import logging

from danceschool.core.constants import getConstant
from .models import EventReminder


# Define logger for this file
logger = logging.getLogger(__name__)


@db_periodic_task(crontab(minute='*'))
def sendReminderEmails():

    if not getConstant('general__enableCronTasks'):
        return

    reminders_needed = EventReminder.objects.filter(**{
        'time__lte': timezone.now(),
        'completed':False,
        'notifyList__isnull': False})
    if reminders_needed:
        for note in reminders_needed:
            for user in note.notifyList.all():
                sent = sendReminderEmailToUser(user,note)
                if sent:
                    # Mark reminder as sent so it won't be sent twice.
                    note.completed = True
                    note.save()
                    logger.info("Email notification sent to user: " + user.first_name + ' ' + user.last_name + ' at ' + user.email)
                else:
                    logger.warning("Unable to send email to user: " + user.first_name + ' ' + user.last_name + ' at ' + user.email)
    else:
        logger.debug("No notifications to send!")
        pass


def sendReminderEmailToUser(user,reminder):
    subject = _('REMINDER: ') + reminder.eventOccurrence.event.name
    subject += ' on ' + reminder.eventOccurrence.startTime.strftime('%A, %B %-d, %Y')
    if not reminder.eventOccurrence.allDay:
        subject += ' at ' + reminder.eventOccurrence.startTime.strftime('%-I:%M %p')

    content = render_to_string('private_events/reminder_emails.html',{
        'name': ' '.join([user.first_name, user.last_name]),
        'event': reminder.eventOccurrence.event,
        'occurrence': reminder.eventOccurrence,
        'businessName': getConstant('contact__businessName'),
    })

    try:
        if getConstant('email__disableSiteEmails') and getConstant('email__enableErrorEmails'):
            sent = send_mail(
                subject,content,
                getConstant('email__defaultEmailFrom'),
                [
                    getConstant('email__errorEmailTo'),
                ],
                fail_silently=False)
        else:
            sent = send_mail(
                subject,content,
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
