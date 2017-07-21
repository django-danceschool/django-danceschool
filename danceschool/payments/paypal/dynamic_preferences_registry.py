'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import FloatPreference, Section
from dynamic_preferences.registries import global_preferences_registry

paypal = Section('paypal',_('Paypal'))


##############################
# Referral Program Preferences
#
@global_preferences_registry.register
class FixedTransactionFee(FloatPreference):
    section = paypal
    name = 'fixedTransactionFee'
    verbose_name = _('Paypal fixed transaction fee')
    help_text = _('Paypal fees consist of a fixed fee plus a percentage of the total price.  When a refund is made, the  the U.S., the variable percentage is refunded, but the fixed fee is not.  In the U.S., this fixed fee is $0.30.  Entering your country\'s fee here ensures that your accounting will remain accurate when you refund students.')
    default = 0.30
