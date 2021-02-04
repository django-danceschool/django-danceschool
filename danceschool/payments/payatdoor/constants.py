from django.conf import settings
from django.utils.translation import gettext as _


# These are the options for accepting payment at the door.  Electronic
# payments are usually handled using the associated payment processor,
# so this usually just refers to cash and check payments.  You can
# specify additional methods by overriding this list in settings.py.
ATTHEDOOR_PAYMENTMETHOD_CHOICES = getattr(
    settings, 'ATTHEDOOR_PAYMENTMETHOD_CHOICES', [
        (_('Cash'), _('Cash')),
        (_('Check'), _('Check')),
    ]
)
