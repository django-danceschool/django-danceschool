from django.conf import settings
from django.core.mail import get_connection, EmailMultiAlternatives
from django.utils import timezone
from django.core.management import call_command

from huey import crontab
from huey.contrib.djhuey import task, db_task, db_periodic_task
from datetime import timedelta

import logging

from .constants import getConstant

# Define logger for this file
logger = logging.getLogger(__name__)


@db_task()
def open_event_registration(event_pk):
    """
    Scheduled task to open registration for an event at a pre-set time.
    Guards against stale state — if the event's status has changed since
    this task was scheduled, updateRegistrationStatus() will handle it correctly.
    """
    from .models import Event

    try:
        event = Event.objects.get(pk=event_pk)
    except Event.DoesNotExist:
        logger.warning('open_event_registration: Event %s not found, skipping.', event_pk)
        return

    logger.info('Opening registration for event %s (scheduled task).', event_pk)
    event.updateRegistrationStatus()


@db_task()
def close_event_registration(event_pk):
    """
    Scheduled task to close registration for an event when it expires.
    Same staleness guard as above.
    """
    from .models import Event

    try:
        event = Event.objects.get(pk=event_pk)
    except Event.DoesNotExist:
        logger.warning('close_event_registration: Event %s not found, skipping.', event_pk)
        return

    logger.info('Closing registration for event %s (scheduled task).', event_pk)
    event.updateRegistrationStatus()


@db_periodic_task(crontab(hour='3', minute='0'))
def dailyRegistrationStatusSafetyNet():
    """
    Nightly safety net — catches any events whose registration status has drifted
    due to missed tasks (e.g. after a Redis restart or worker downtime).
    Runs at 3am to minimize user-facing impact.
    """
    from .models import Event
    from danceschool.core.constants import getConstant

    if not getConstant('general__enableCronTasks'):
        return

    logger.info('Running nightly registration status safety net check.')

    # Check all non-definitively-closed events, not just open ones,
    # so we catch events that should have opened but didn't.
    watchable_statuses = ['O', 'H', 'L']  # enabled, heldOpen, linkOnly
    events = Event.objects.filter(status__in=watchable_statuses)

    for event in events:
        modified, _ = event.updateRegistrationStatus()
        if modified:
            logger.info('Safety net corrected registration status for event %s.', event.pk)


@db_periodic_task(crontab(minute='*/60'))
def clearExpiredInvoices():
    '''
    Every hour, look for unfinished invoices that have expired and delete them.
    To ensure that there are no issues that arise from slight differences between
    session expiration dates and invoice expiration dates, only
    delete instances that have been expired for a specific length of time.
    '''
    from .models import Invoice

    if not getConstant('general__enableCronTasks'):
        return

    if getConstant('registration__deleteExpiredInvoices'):
        Invoice.objects.filter(
            status=Invoice.PaymentStatus.preliminary,
            expirationDate__lte=(
                timezone.now() -
                timedelta(minutes=getConstant('registration__retainExpiredInvoicesMinutes'))
            )
        ).delete()
        call_command('clearsessions')


@task(retries=3)
def sendEmail(
    subject, content, from_address, from_name='', to=[], cc=[], bcc=[],
    attachment_name='attachment', attachment=None, html_content=None
):
    # Ensure that email address information is in list form and that there are no empty values
    recipients = [x for x in to + cc if x]
    bcc = [x for x in bcc if x]
    from_email = from_name + ' <' + from_address + '>' if from_address else None
    reply_to = [from_address, ] if from_address else None

    logger.info('Sending email from %s to %s' % (from_address, recipients))

    if getattr(settings, 'DEBUG', None):
        logger.info('Email content:\n\n%s' % content)
        logger.info('Email HTML content:\n\n%s' % html_content)

    with get_connection() as connection:
        connection.open()

        message = EmailMultiAlternatives(
            subject=subject,
            body=content,
            from_email=from_email,
            to=recipients,
            bcc=bcc,
            reply_to=reply_to,
            connection=connection,
        )

        if html_content:
            message.attach_alternative(html_content, "text/html")

        if attachment:
            message.attach(attachment_name, attachment)

        message.send(fail_silently=False)
        connection.close()
