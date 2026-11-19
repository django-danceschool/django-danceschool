from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme

import logging
from itertools import chain

from .constants import getConstant
from .signals import collect_purchasable_items


# Define logger for this file
logger = logging.getLogger(__name__)


def getLocalUrl(request, url, fallback):
    '''
    Return url if it is a page on this site, and otherwise fallback.  Use
    this for any URL that comes from the browser before redirecting to it.
    '''
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return fallback


def getPluginSuccessUrl(model, plugin_id):
    '''
    The URL of the success page of the payment form plugin instance of this
    model with this id, or None if there is no such instance or it has no
    success page.  Payment processors look this up on the server, rather
    than accepting a success URL from the browser, so that it cannot be used
    to send the payer to another site.
    '''
    try:
        instance = model.objects.get(id=int(plugin_id))
    except (TypeError, ValueError, ObjectDoesNotExist):
        return None
    if instance.successPage:
        return instance.successPage.get_absolute_url()
    return None


def getSiteUrl():
    return '%s://%s' % (
        getConstant('email__linkProtocol'),
        Site.objects.get_current().domain,
    )


def emailErrorMessage(subject, message):
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
        send_mail(subject, message,
                  send_from,
                  [send_to], fail_silently=False)
        logger.debug('Error email sent.')
    except Exception as e:
        logger.error('Error email was not sent: %s' % e)


def getReturnPage(siteHistory, prior=False):
    '''
    This helper function is called in various places to get the return page from current
    session data.  The session data (in the 'SITE_HISTORY' key) is a required argument.
    '''

    expiry = parse_datetime(
        siteHistory.get('expiry', ''),
    )
    if prior:
        returnPage = siteHistory.get('priorPage', None)
        returnPageName = siteHistory.get('priorPageName', None)
    else:
        returnPage = siteHistory.get('returnPage', None)
        returnPageName = siteHistory.get('returnPageName', None)

    if expiry and expiry >= timezone.now() and returnPage[0]:
        return {
            'url': reverse(returnPage[0], kwargs=returnPage[1]),
            'title': returnPageName,
        }
    else:
        return {'url': None, 'title': None}


def getPurchasableItems(sender=None, request=None, payAtDoor=False):
    """
    Returns an iterable of (instance, serializer) pairs collected via signal
    handlers. Can be used by both views and internal logic.
    """
    responses = collect_purchasable_items.send(
        sender=sender, request=request, payAtDoor=payAtDoor
    )

    collected = []
    for receiver, result in responses:
        if not result:
            continue
        qs, serializer_class = result
        if qs.exists():
            collected.append((qs, serializer_class))
    return collected
