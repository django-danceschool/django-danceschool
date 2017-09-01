'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''
from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, IntegerPreference, ModelChoicePreference, Section
from dynamic_preferences.registries import global_preferences_registry

from .models import ExpenseCategory, RevenueCategory

# we create some section objects to link related preferences together

financial = Section('financial',_('Financial App'))


##############################
# Referral Program Preferences
#
@global_preferences_registry.register
class GenerateEventStaffExpensesEnabled(BooleanPreference):
    section = financial
    name = 'autoGenerateExpensesEventStaff'
    verbose_name = _('Auto-generate ExpenseItems for completed events')
    help_text = _('Uncheck to disable the automatic generation of ExpenseItems for class series instructors in the financial app.')
    default = True


@global_preferences_registry.register
class GenerateVenueExpensesEnabled(BooleanPreference):
    section = financial
    name = 'autoGenerateExpensesVenueRental'
    verbose_name = _('Auto-generate ExpenseItems for venue rental')
    help_text = _('Uncheck to disable the automatic generation of ExpenseItems for venue rental in the financial app.')
    default = True


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
class ClassInstructionCat(ModelChoicePreference):
    section = financial
    name = 'classInstructionExpenseCat'
    verbose_name = _('Expense Category for Class Instruction items')
    model = ExpenseCategory
    queryset = ExpenseCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return ExpenseCategory.objects.get_or_create(name=_('Class Instruction'))[0]


@global_preferences_registry.register
class AssistantClassInstructionCat(ModelChoicePreference):
    section = financial
    name = 'assistantClassInstructionExpenseCat'
    verbose_name = _('Expense Category for Assistant Class Instruction items')
    model = ExpenseCategory
    queryset = ExpenseCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return ExpenseCategory.objects.get_or_create(name=_('Assistant Class Instruction'))[0]


@global_preferences_registry.register
class OtherStaffExpenseCat(ModelChoicePreference):
    section = financial
    name = 'otherStaffExpenseCat'
    verbose_name = _('Expense Category for other Event-Related Staff Expenses')
    model = ExpenseCategory
    queryset = ExpenseCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return ExpenseCategory.objects.get_or_create(name=_('Other Event-Related Staff Expenses'))[0]


@global_preferences_registry.register
class VenueRentalCat(ModelChoicePreference):
    section = financial
    name = 'venueRentalExpenseCat'
    verbose_name = _('Expense Category for Venue Rental')
    model = ExpenseCategory
    queryset = ExpenseCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return ExpenseCategory.objects.get_or_create(name=_('Venue Rental'))[0]


@global_preferences_registry.register
class RegistrationsCat(ModelChoicePreference):
    section = financial
    name = 'registrationsRevenueCat'
    verbose_name = _('Revenue Category for Registrations')
    model = RevenueCategory
    queryset = RevenueCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return RevenueCategory.objects.get_or_create(name=_('Registrations'))[0]


@global_preferences_registry.register
class GiftCertCat(ModelChoicePreference):
    section = financial
    name = 'giftCertRevenueCat'
    verbose_name = _('Revenue Category for Purchased Vouchers and Gift Certificates')
    model = RevenueCategory
    queryset = RevenueCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return RevenueCategory.objects.get_or_create(name=_('Purchased Vouchers/Gift Certificates'))[0]


@global_preferences_registry.register
class UnallocatedPaymentsCat(ModelChoicePreference):
    section = financial
    name = 'unallocatedPaymentsRevenueCat'
    verbose_name = _('Revenue Category for Unknown and Otherwise Unallocated Online Payments')
    model = RevenueCategory
    queryset = RevenueCategory.objects.all()

    def get_default(self):
        # if self.model and self.model._meta.db_table in connection.introspection.table_names():
        return RevenueCategory.objects.get_or_create(name=_('Unallocated Online Payments'))[0]
