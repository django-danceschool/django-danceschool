# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from danceschool.core.utils.sys import isPreliminaryRun


class FinancialAppConfig(AppConfig):
    name = 'danceschool.financial'
    verbose_name = _('Financial Functions')

    def ready(self):
        from django.core.exceptions import ValidationError
        from django.db import connection

        from danceschool.core.models import Event, SubstituteTeacher, Registration, EventRegistration
        from danceschool.core.constants import getConstant, updateConstant

        from . import constants

        # Add some properties that are useful for the series checkin process.
        # Note that all of these properties are written in a way that depends
        # on revenue items being linked to registrations both directly _and_
        # also through the eventregistration objects.
        # This works because it is set in the save() method of the RevenueItem
        # model.  However, if you process revenue in a way such that save() is
        # not called, then things will break.

        @property
        def cashReported(self):
            ''' Add a property to Registrations indicating how much cash revenue has been reported. '''
            return sum([x.netRevenue for x in self.revenueitem_set.filter(paymentMethod=constants.CASH_PAYMENTMETHOD_ID)])
        Registration.add_to_class('cashReported', cashReported)
        EventRegistration.add_to_class('cashReported', cashReported)

        @property
        def cashReceived(self):
            ''' Add a property to Registrations indicating how much cash has been both reported and marked as received. '''
            return sum([x.netRevenue for x in self.revenueitem_set.filter(paymentMethod=constants.CASH_PAYMENTMETHOD_ID,received=True)])
        Registration.add_to_class('cashReceived', cashReceived)
        EventRegistration.add_to_class('cashReceived', cashReceived)

        @property
        def paypalReported(self):
            ''' Add a property to Registrations indicating how much Paypal revenue has been reported (in the financials app). '''
            return sum([x.netRevenue for x in self.revenueitem_set.filter(paymentMethod=constants.PAYPAL_PAYMENTMETHOD_ID)])
        Registration.add_to_class('paypalReported', paypalReported)
        EventRegistration.add_to_class('paypalReported', paypalReported)

        @property
        def paypalReceived(self):
            return sum([x.netRevenue for x in self.revenueitem_set.filter(paymentMethod=constants.PAYPAL_PAYMENTMETHOD_ID,received=True)])
        Registration.add_to_class('paypalReceived',paypalReceived)
        EventRegistration.add_to_class('paypalReceived',paypalReceived)

        @property
        def refundableReceived(self):
            ''' Total amount received by auto-refundable payment methods. '''
            return sum([x.netRevenue for x in self.revenueitem_set.filter(paymentMethod__in=constants.REVENUE_AUTOREFUND_PAYMENTMETHODS,received=True)])
        Registration.add_to_class('refundableReceived',refundableReceived)
        EventRegistration.add_to_class('refundableReceived',refundableReceived)

        @property
        def paypalReceivedInApp(self):
            '''
            Add a property to Registrations indicating how much Paypal revenue has been received.
            There is only one directly related Paypal transaction for each registration, but the
            netRevenue method takes account of any transactions that are related to the initial one,
            and the Paypal app should ensure that any refund type transactions are automatically linked.
            Manual secondary transactions must be manually linked in the Paypal app.
            '''
            if hasattr(self,'ipnmessage'):
                return self.ipnmessage.netRevenue
            else:
                return 0
        Registration.add_to_class('paypalReceivedInApp',paypalReceivedInApp)

        @property
        def paypalMismatch(self):
            ''' Add a property indicating that the IPN Paypal total and the recorded revenue total do not match '''
            return round(self.paypalReported - self.paypalReceived,2) != 0 or round(self.paypalReceived - self.paypalReceivedInApp,2) != 0
        Registration.add_to_class('paypalMismatch',paypalMismatch)

        @property
        def paypalUnallocatedRefunds(self):
            if hasattr(self,'ipnmessage'):
                return self.ipnmessage.unallocatedRefunds
            else:
                return 0
        Registration.add_to_class('paypalUnallocatedRefunds',paypalUnallocatedRefunds)

        @property
        def revenueReportedGross(self):
            return sum([x.total for x in self.revenueitem_set.all()])
        Registration.add_to_class('revenueReportedGross',revenueReportedGross)
        EventRegistration.add_to_class('revenueReportedGross',revenueReportedGross)

        @property
        def revenueReported(self):
            return sum([x.netRevenue for x in self.revenueitem_set.all()])
        Registration.add_to_class('revenueReported',revenueReported)
        EventRegistration.add_to_class('revenueReported',revenueReported)

        @property
        def feesReported(self):
            return sum([x.fees for x in self.revenueitem_set.all()])
        Registration.add_to_class('feesReported',feesReported)
        EventRegistration.add_to_class('feesReported',feesReported)

        @property
        def revenueReceivedGross(self):
            return sum([x.total for x in self.revenueitem_set.filter(received=True)])
        Registration.add_to_class('revenueReceivedGross',revenueReceivedGross)
        EventRegistration.add_to_class('revenueReceivedGross',revenueReceivedGross)

        @property
        def revenueReceived(self):
            return sum([x.netRevenue for x in self.revenueitem_set.filter(received=True)])
        Registration.add_to_class('revenueReceived',revenueReceived)
        EventRegistration.add_to_class('revenueReceived',revenueReceived)

        @property
        def revenueMismatch(self):
            return round(self.netPrice,2) != round(self.revenueReported + self.feesReported + self.revenueRefundsReported,2)
        EventRegistration.add_to_class('revenueMismatch',revenueMismatch)
        Registration.add_to_class('revenueMismatch',revenueMismatch)

        @property
        def revenueNotYetReceived(self):
            return self.revenueReceived != self.revenueReported
        EventRegistration.add_to_class('revenueNotYetReceived',revenueNotYetReceived)
        Registration.add_to_class('revenueNotYetReceived',revenueNotYetReceived)

        @property
        def revenueRefundsReported(self):
            return -1 * sum([x.adjustments for x in self.revenueitem_set.all()])
        EventRegistration.add_to_class('revenueRefundsReported',revenueRefundsReported)
        Registration.add_to_class('revenueRefundsReported',revenueRefundsReported)

        # Add a property and a validator to check for and validate that teachers have not
        # already been paid when accepting SubstituteTeacher submissions.
        @property
        def paidOut(self):
            ''' Add a property to Series indicating whether it has been paid out. '''
            return (True in self.expenseitem_set.filter(eventstaffmember__isnull=False).values_list('paid',flat=True))
        Event.add_to_class('paidOut', paidOut)

        def validate_EnsureNotPaidOut(event_pk):
            ''' Add a validator to SubstituteTeacher submissions checking if the series has been paid out '''
            event = Event.objects.get(pk=event_pk)
            if event.paidOut:
                raise ValidationError(_('Staff members for this series have already been paid.  If you need to adjust hours worked, you will need to request money from them directly.'))

        for field in [f for f in SubstituteTeacher._meta.fields if f.name == 'event']:
            field.validators.append(validate_EnsureNotPaidOut)

        # This ensures that the receivers are loaded.
        from . import handlers

        # Add get_or_create calls to ensure that the Expense and Revenue categories needed
        # for our handlers exist.  Other categories can always be created, and these can be
        # modified in the database.
        if 'financial_expensecategory' in connection.introspection.table_names() and not isPreliminaryRun():
            ExpenseCategory = self.get_model('ExpenseCategory')

            # Name, preference key, and defaultRate
            new_expense_cats = [
                (_('Class Instruction'),'financial__classInstructionExpenseCatID',0),
                (_('Assistant Class Instruction'),'financial__assistantClassInstructionExpenseCatID',0),
                (_('Other Event-Related Staff Expenses'),'financial__otherStaffExpenseCatID',0),
                (_('Venue Rental'),'financial__venueRentalExpenseCatID',None),
            ]

            for cat in new_expense_cats:
                if (getConstant(cat[1]) or 0) <= 0:
                    new_cat, created = ExpenseCategory.objects.get_or_create(
                        name=cat[0],
                        defaults={'defaultRate': cat[2]},
                    )
                    # Update constant and fail silently
                    updateConstant(cat[1],new_cat.id,True)

        if 'financial_revenuecategory' in connection.introspection.table_names() and not isPreliminaryRun():
            RevenueCategory = self.get_model('RevenueCategory')

            # Name and preference key
            new_revenue_cats = [
                (_('Registrations'),'financial__registrationsRevenueCatID'),
                (_('Purchased Vouchers/Gift Certificates'),'financial__giftCertRevenueCatID'),
                (_('Unallocated Online Payments'),'financial__unallocatedPaymentsRevenueCatID'),
            ]

            for cat in new_revenue_cats:
                if (getConstant(cat[1]) or 0) <= 0:
                    new_cat, created = RevenueCategory.objects.get_or_create(name=cat[0])
                    # Update constant and fail silently
                    updateConstant(cat[1],new_cat.id,True)
