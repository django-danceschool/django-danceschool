'''
The client for PayPal's REST API (the v2 Orders and Payments APIs), using
PayPal's paypal-server-sdk package.
'''
from django.conf import settings

from paypalserversdk.configuration import Environment
from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient


def get_client():
    '''
    A client configured from the PAYPAL_MODE ("sandbox" or "live"),
    PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET settings.
    '''
    if getattr(settings, 'PAYPAL_MODE', 'sandbox') == 'live':
        environment = Environment.PRODUCTION
    else:
        environment = Environment.SANDBOX

    return PaypalServersdkClient(
        client_credentials_auth_credentials=ClientCredentialsAuthCredentials(
            o_auth_client_id=getattr(settings, 'PAYPAL_CLIENT_ID', ''),
            o_auth_client_secret=getattr(settings, 'PAYPAL_CLIENT_SECRET', ''),
        ),
        environment=environment,
    )


def error_message(exception):
    ''' A short description of an error from the PayPal API, for logs and staff. '''
    response = getattr(exception, 'response', None)
    status = getattr(response, 'status_code', None)
    reason = getattr(exception, 'reason', None) or str(exception)
    return '%s%s' % (reason, ' (HTTP %s)' % status if status else '')
