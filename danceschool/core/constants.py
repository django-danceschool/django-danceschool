from django.db import connection
from django.conf import settings
from django.utils.translation import gettext_lazy as _

import logging
from dynamic_preferences.registries import global_preferences_registry
from dynamic_preferences.exceptions import NotFoundInRegistry
from .utils.sys import isPreliminaryRun


# Define logger for this file
logger = logging.getLogger(__name__)


def getConstant(name):
    '''
    This is a convenience function that makes it easy to access the value of a preference/constant
    without needing to check if the django_dynamic_preferences app has been set up and without
    needing to load from that model directly.
    '''

    # We instantiate a manager for our global preferences
    if 'dynamic_preferences_globalpreferencemodel' in connection.introspection.table_names() and not isPreliminaryRun():
        params = global_preferences_registry.manager()
        try:
            return params.get(name)
        except NotFoundInRegistry as e:
            logger.error('Error in getting constant: %s' % e)
            return None


def updateConstant(name, value, fail_silently=False):
    '''
    This is a convenience function that makes it easy to update the value of a preference/constant
    without needing to check if the django_dynamic_preferences app has been set up, without
    needing to load from that model directly, and with the option to suppress any errors
    (e.g. KeyErrors resulting from the order in which apps are loaded).
    '''

    # We instantiate a manager for our global preferences
    if 'dynamic_preferences_globalpreferencemodel' in connection.introspection.table_names() and not isPreliminaryRun():
        params = global_preferences_registry.manager()
        try:
            params[name] = value
            return True
        except Exception as e:
            logger.error('Error in updating constant: %s' % e)
            if not fail_silently:
                raise
            return False


# These are the options for the optional question re: how the person
# heard about us.  If you want different choices, this list can be
# overridden in your project's settings.py.
HOW_HEARD_CHOICES = getattr(settings, 'HOW_HEARD_CHOICES', [
    ('', '------'),
    ('Previous Student', _('I\'ve Taken Classes Before')),
    ('Facebook', _('Facebook')),
    ('Flyers', _('Flyers/Cards')),
    ('Friend', _('Another Student')),
    ('Other', _('Other')),
])


# Validation strings for information that is kept in session data.  It is unlikely
# that you will want to change these, but it can be done in settings to avoid conflicts.
REG_VALIDATION_STR = getattr(settings, 'REG_VALIDATION_STR', 'danceschool_registration')
EMAIL_VALIDATION_STR = getattr(settings, 'EMAIL_VALIDATION_STR', 'sendEmailView')
REFUND_VALIDATION_STR = getattr(settings, 'REFUND_VALIDATION_STR', 'refundProcessingView')
PAYMENT_VALIDATION_STR = getattr(settings, 'PAYMENT_VALIDATION_STR', 'danceschool_payment')
