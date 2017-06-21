import logging

from django.core.mail import send_mail

from .constants import getConstant


# Define logger for this file
logger = logging.getLogger(__name__)


def emailErrorMessage(subject,message):
    '''
    Useful for sending error messages via email.
    '''
    if not getConstant('email__enableErrorEmails'):
        logger.info('Not sending error email: error emails are not enabled.')
        return

    send_from = getConstant('email__errorEmailFrom')
    send_to = getConstant('email__errorEmailTo')

    if not send_from or not send_to:
        logger.error('Cannot send error emails because addresses have not been specified.')
        return

    try:
        send_mail(subject,message,
                  send_from,
                  [send_to], fail_silently=False)
        logger.debug('Error email sent.')
    except Exception as e:
        logger.error('Error email was not sent: %s' % e)
