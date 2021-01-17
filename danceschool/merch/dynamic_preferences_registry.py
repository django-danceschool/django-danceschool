'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import (
    BooleanPreference, FloatPreference, Section
)
from dynamic_preferences.registries import global_preferences_registry


registration = Section('registration', _('Registration'))


@global_preferences_registry.register
class SalesTaxRate(FloatPreference):
    section = registration
    name = 'merchSalesTaxRate'
    verbose_name = _('Sales tax percentage rate to be applied to merchandise.')
    help_text = _(
        'Enter, e.g. \'10\' for a 10% tax rate to be applied to all merchandise. ' +
        'This can be overridden for each individual merchandise item.'
    )
    default = 0.0


@global_preferences_registry.register
class BuyerPaysSalesTax(BooleanPreference):
    section = registration
    name = 'merchBuyerPaysSalesTax'
    verbose_name = _('Buyer pays sales tax (added to total price) for merchandise')
    help_text = _(
        'If unchecked, then the buyer will not be charged sales tax directly, ' +
        'but the amount of tax collected by the business will be reported.'
    )
    default = True
