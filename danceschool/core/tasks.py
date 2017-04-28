from django.conf import settings
from django.core.mail import get_connection, EmailMessage

from huey.contrib.djhuey import crontab, task, db_periodic_task

import logging

from .models import Series


# Define logger for this file
logger = logging.getLogger(__name__)


@db_periodic_task(crontab(minute='*/60'))
def updateSeriesRegistrationStatus():
    '''
    Every hour, check if the series that are currently open for registration
    should be closed.
    '''
    logger.info('Checking status of Series that are open for registration.')

    open_series = Series.objects.filter().filter(**{'registrationOpen': True})

    for series in open_series:
        series.updateRegistrationStatus()


@task(retries=3)
def sendEmail(subject,content,from_address,from_name='',to=[],cc=[],bcc=[],attachment_name='attachment',attachment=None):
    # Ensure that email address information is in list form.
    recipients = [x for x in to + cc if x]
    logger.info('Sending email from %s to %s' % (from_address,recipients))

    if settings.IS_LOCAL_WEBSERVER or settings.DEBUG:
        logger.info('Email content:\n\n%s' % content)
    if settings.IS_LOCAL_WEBSERVER:
        logger.info('Not sending email because IS_LOCAL_WEBSERVER is enabled.')
        return

    with get_connection() as connection:
        connection.open()

        message = EmailMessage(
            subject=subject,
            body=content,
            from_email=from_name + ' <' + from_address + '>',
            to=recipients,
            bcc=bcc,
            reply_to=[from_address],
            connection=connection,
        )

        if attachment:
            message.attach(attachment_name, attachment)

    message.send(fail_silently=False)
    connection.close()
