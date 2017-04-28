'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.forms import HiddenInput
from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, IntegerPreference, Section
from dynamic_preferences.registries import global_preferences_registry

# we create some section objects to link related preferences together

financial = Section('financial',_('Financial App'))


##############################
# Referral Program Preferences
#
@global_preferences_registry.register
class GenerateEventStaffExpensesEnabled(BooleanPreference):
    section = financial
    name = 'autoGenerateExpensesCompletedEvents'
    verbose_name = _('Auto-generate ExpenseItems for completed events')
    help_text = _('Uncheck to disable the automatic generation of ExpenseItems for class series instructors in the financial app.')
    default = True


@global_preferences_registry.register
class GenerateEventStaffExpensesWindow(IntegerPreference):
    section = financial
    name = 'autoGenerateExpensesCompletedEventsWindow'
    verbose_name = _('Completed events autogeneration window (months)')
    help_text = _('Set how many months back back from the date of execution to autogenerate ExpenseItems for class series instructors in the financial app, or set to 0 to autogenerate with no time restriction.')
    default = 0


@global_preferences_registry.register
class GenerateVenueExpensesEnabled(BooleanPreference):
    section = financial
    name = 'autoGenerateExpensesVenueRental'
    verbose_name = _('Auto-generate ExpenseItems for venue rental')
    help_text = _('Uncheck to disable the automatic generation of ExpenseItems for venue rental in the financial app.')
    default = True


@global_preferences_registry.register
class GenerateVenueExpensesWindow(IntegerPreference):
    section = financial
    name = 'autoGenerateExpensesVenueRentalWindow'
    verbose_name = _('Venue rental autogeneration window (months)')
    help_text = _('Set how many months back back from the date of execution to autogenerate ExpenseItems for venue rental in the financial app, or set to 0 to autogenerate with no time restriction.')
    default = 0


@global_preferences_registry.register
class GenerateRegistrationRevenuesEnabled(BooleanPreference):
    section = financial
    name = 'autoGenerateRevenueRegistrations'
    verbose_name = _('Auto-generate RevenueItems for registrations')
    help_text = _('Uncheck to disable the automatic generation of RevenueItems for old Registrations in the financial app (useful when migrating old DBs).')
    default = True


@global_preferences_registry.register
class GenerateRegistrationRevenuesWindow(IntegerPreference):
    section = financial
    name = 'autoGenerateRevenueRegistrationsWindow'
    verbose_name = _('Registration revenue autogeneration window (months)')
    help_text = _('Set how many months back back from the date of execution to autogenerate RevenueItems for old Registrations in the financial app, or set to 0 to autogenerate with no time restriction.')
    default = 0


@global_preferences_registry.register
class ClassInstructionCatID(IntegerPreference):
    section = financial
    name = 'classInstructionExpenseCatID'
    help_text = _('The ExpenseCategory ID for Class Instruction items')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class AssistantClassInstructionCatID(IntegerPreference):
    section = financial
    name = 'assistantClassInstructionExpenseCatID'
    help_text = _('The ExpenseCategory ID for Assistant Class Instruction items')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class OtherStaffExpenseCatID(IntegerPreference):
    section = financial
    name = 'otherStaffExpenseCatID'
    help_text = _('The ExpenseCategory ID for other Event-Related Staff Expenses')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class VenueRentalCatID(IntegerPreference):
    section = financial
    name = 'venueRentalExpenseCatID'
    help_text = _('The ExpenseCategory ID for Venue Rental')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class RegistrationsCatID(IntegerPreference):
    section = financial
    name = 'registrationsRevenueCatID'
    help_text = _('The RevenueCategory ID for Registrations')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class GiftCertCatID(IntegerPreference):
    section = financial
    name = 'giftCertRevenueCatID'
    help_text = _('The RevenueCategory ID for Purchased Vouchers and Gift Certificates')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0


@global_preferences_registry.register
class UnallocatedPaymentsCatID(IntegerPreference):
    section = financial
    name = 'unallocatedPaymentsRevenueCatID'
    help_text = _('The RevenueCategory ID for Unknown and Otherwise Unallocated Online Payments')
    widget = HiddenInput

    # This is automatically updated by apps.py
    default = 0
