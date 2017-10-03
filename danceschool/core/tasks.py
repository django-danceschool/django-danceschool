from django.conf import settings
from django.core.mail import get_connection, EmailMultiAlternatives
from django.utils import timezone
from django.core.management import call_command

from huey import crontab
from huey.contrib.djhuey import task, db_periodic_task
from datetime import timedelta

import logging

from .constants import getConstant

# Define logger for this file
logger = logging.getLogger(__name__)


@db_periodic_task(crontab(minute='*/60'))
def updateSeriesRegistrationStatus():
    '''
    Every hour, check if the series that are currently open for registration
    should be closed.
    '''
    from .models import Series

    if not getConstant('general__enableCronTasks'):
        return

    logger.info('Checking status of Series that are open for registration.')

    open_series = Series.objects.filter().filter(**{'registrationOpen': True})

    for series in open_series:
        series.updateRegistrationStatus()


@db_periodic_task(crontab(minute='*/60'))
def clearExpiredTemporaryRegistrations():
    '''
    Every hour, look for TemporaryRegistrations that have expired and delete them.
    To ensure that there are no issues that arise from slight differences between
    session expiration dates and TemporaryRegistration expiration dates, only
    delete instances that have been expired for one minute.
    '''
    from .models import TemporaryRegistration

    if not getConstant('general__enableCronTasks'):
        return

    if getConstant('registration__deleteExpiredTemporaryRegistrations'):
        TemporaryRegistration.objects.filter(expirationDate__lte=timezone.now() - timedelta(minutes=1)).delete()
        call_command('clearsessions')


@task(retries=3)
def sendEmail(subject,content,from_address,from_name='',to=[],cc=[],bcc=[],attachment_name='attachment',attachment=None,html_content=None):
    # Ensure that email address information is in list form and that there are no empty values
    recipients = [x for x in to + cc if x]
    bcc = [x for x in bcc if x]
    from_email = from_name + ' <' + from_address + '>' if from_address else None
    reply_to = [from_address,] if from_address else None

    logger.info('Sending email from %s to %s' % (from_address,recipients))

    if getattr(settings,'DEBUG',None):
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
