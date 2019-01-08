from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

import logging

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


def getReturnPage(siteHistory,prior=False):
    '''
    This helper function is called in various places to get the return page from current
    session data.  The session data (in the 'SITE_HISTORY' key) is a required argument.
    '''

    expiry = parse_datetime(
        siteHistory.get('expiry',''),
    )
    if prior:
        returnPage = siteHistory.get('priorPage',None)
        returnPageName = siteHistory.get('priorPageName',None)
    else:
        returnPage = siteHistory.get('returnPage',None)
        returnPageName = siteHistory.get('returnPageName',None)

    if expiry and expiry >= timezone.now() and returnPage:
        return {
            'url': reverse(returnPage[0],kwargs=returnPage[1]),
            'title': returnPageName,
        }
    else:
        return {'url': None, 'title': None}
