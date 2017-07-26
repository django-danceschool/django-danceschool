from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.encoding import python_2_unicode_compatible
from django.core.validators import MinValueValidator
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from filer.fields.file import FilerFileField
from filer.models import Folder

from danceschool.core.models import EventStaffMember, Event, InvoiceItem, Location
from danceschool.core.constants import getConstant


@python_2_unicode_compatible
class ExpenseCategory(models.Model):
    '''
    These are the different available categories of payment
    '''

    name = models.CharField(_('Name'),max_length=50,unique=True,help_text=_('Different types of tasks and payments should have different category names'))
    defaultRate = models.FloatField(_('Default rate'),help_text=_('This is the default hourly payment rate for this type of task.  For staff expenses and venue rentals, this will be overridden by the rate specified as default for the venue or staff type.'),null=True,blank=True,validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Expense category')
        verbose_name_plural = _('Expense categories')


@python_2_unicode_compatible
class ExpenseItem(models.Model):
    '''
    Expenses may be associated with EventStaff or with Events, or they may be associated with nothing
    '''

    submissionUser = models.ForeignKey(User,verbose_name=_('Submission user'),related_name='expensessubmittedby',null=True, blank=True)
    submissionDate = models.DateTimeField(_('Submission date'),auto_now_add=True)

    category = models.ForeignKey(ExpenseCategory,verbose_name=_('Category'))

    description = models.CharField(_('Description'),max_length=200,null=True,blank=True)

    hours = models.FloatField(_('Hours'),help_text=_('Please indicate the number of hours to be paid for.'),null=True,blank=True,validators=[MinValueValidator(0)])
    wageRate = models.FloatField(_('Wage rate'),help_text=_('This should be filled automatically, but can be changed as needed.'),null=True,blank=True,validators=[MinValueValidator(0)])
    total = models.FloatField(_('Total amount'),null=True,blank=True,validators=[MinValueValidator(0)])
    adjustments = models.FloatField(_('Adjustments/refunds'),help_text=_('Record any ex-post adjustments to the amount (e.g. refunds) in this field. A positive amount increases the netExpense, a negative amount reduces the netExpense.'),default=0)
    fees = models.FloatField(_('Fees'),help_text=_('The sum of any transaction fees (e.g. Paypal fees) that were paid <strong>by us</strong>, and should therefore be added to net expense.'),default=0)

    paymentMethod = models.CharField(_('Payment method'),max_length=50,null=True,blank=True)

    comments = models.TextField(_('Comments/Notes'),null=True,blank=True)
    # attachment = models.FileField('Attach File (optional)',null=True,blank=True,max_length=200,storage=PrivateMediaStorage(),upload_to='board/expenses/%Y/%m/')
    attachment = FilerFileField(verbose_name=_('Attach File (optional)'),null=True,blank=True,related_name='expense_attachment')

    # These are foreign key relations for the things that expenses can be be related to.
    # An expense item should only be populated by one of eventstaffmember
    # or eventvenue.  However, an event will automatically be populated by the associated
    # event if it is a determined event expense.  This allows for simpler lookups,
    # like, "get all expenses associated with this event."
    eventstaffmember = models.OneToOneField(EventStaffMember,null=True,blank=True,verbose_name=_('Staff member'))

    eventvenue = models.ForeignKey(Event,null=True,blank=True,related_name='venueexpense',verbose_name=_('Event venue'))
    event = models.ForeignKey(Event,null=True,blank=True,verbose_name=_('Event'),help_text=_('If this item is associated with an Event, enter it here.'))

    payToUser = models.ForeignKey(User,null=True,blank=True,related_name='payToUser',verbose_name=_('Pay to user'))
    payToLocation = models.ForeignKey(Location,null=True,blank=True,verbose_name=_('Pay to location'))
    payToName = models.CharField(_('Pay to (enter name)'),max_length=50, null=True,blank=True)

    reimbursement = models.BooleanField(_('Reimbursement'),help_text=_('Check to indicate that this is a reimbursement expense (i.e. not compensation).'),default=False)

    approved = models.BooleanField(_('Approved'),help_text=_('Check to indicate that expense is approved for payment.'),default=False)
    paid = models.BooleanField(_('Paid'),help_text=_('Check to indicate that payment has been made.'),default=False)

    approvalDate = models.DateTimeField(_('Approval date'),null=True,blank=True)
    paymentDate = models.DateTimeField(_('Payment date'),null=True,blank=True)

    # This field is used to aggregate expenses over time (e.g. by month).
    # The value of this field is auto-updated using pre-save methods. If
    # there is a class series or an event associated with this expense,
    # then the value is taken from that.  Otherwise, the submission date
    # is used.
    accrualDate = models.DateTimeField(_('Accrual date'))

    @property
    def netExpense(self):
        return self.total + self.adjustments + self.fees
    netExpense.fget.short_description = _('Net expense')

    @property
    def payTo(self):
        '''
        Returns a string indicating who the expense is to be paid to.
        For more convenient references of miscellaneous expenses.
        '''
        if self.payToUser:
            return ' '.join([self.payToUser.first_name,self.payToUser.last_name])
        elif self.payToLocation:
            return self.payToLocation.name
        else:
            return self.payToName or ''
    payTo.fget.short_description = _('Pay to')

    def save(self, *args, **kwargs):
        '''
        This custom save method ensures that an expense is not attributed to multiple categories.
        It also ensures that the series and event properties are always associated with any
        type of expense of that series or event.
        '''
        # Set the approval and payment dates if they have just been approved/paid.
        if not hasattr(self,'__paid') or not hasattr(self,'__approved'):
            if self.approved and not self.approvalDate:
                self.approvalDate = timezone.now()
            if self.paid and not self.paymentDate:
                self.paymentDate = timezone.now()
        else:
            if self.approved and not self.approvalDate and not self.__approvalDate:
                self.approvalDate = timezone.now()
            if self.paid and not self.paymentDate and not self.__paymentDate:
                self.paymentDate = timezone.now()

        # Ensure that each expense is attribued to only one series or event.
        if len([x for x in [
                self.eventstaffmember,
                self.eventvenue,] if x]) > 1:
            raise ValidationError(_('This expense cannot be attributed to multiple categories.'),code='invalid')

        # Fill out the series and event properties to permit easy calculation of
        # revenues and expenses by series or by event.
        if self.eventstaffmember:
            self.event = self.eventstaffmember.event
            if hasattr(self.eventstaffmember.staffMember,'userAccount'):
                self.payToUser = self.eventstaffmember.staffMember.userAccount
        if self.eventvenue:
            self.event = self.eventvenue
            self.payToLocation = self.eventvenue.location

        # Set the accrual date.  The method for events ensures that the accrualDate month
        # is the same as the reported month of the series/event by accruing to the end date of the last
        # class or occurrence in that month.
        if not self.accrualDate:
            if self.event and self.event.month:
                self.accrualDate = self.event.eventoccurrence_set.order_by('endTime').filter(**{'endTime__month': self.event.month}).last().endTime
            else:
                self.accrualDate = self.submissionDate

        # Set the total for hourly work
        if self.hours and not self.wageRate and not self.total and not self.payToLocation and self.category:
            self.wageRate = self.category.defaultRate
        elif self.hours and not self.wageRate and not self.total and self.payToLocation:
            self.wageRate = self.payToLocation.rentalRate

        if self.hours and self.wageRate and not self.total:
            self.total = self.hours * self.wageRate

        super(ExpenseItem, self).save(*args, **kwargs)
        self.__approved = self.approved
        self.__paid = self.paid
        self.__approvalDate = self.approvalDate
        self.__paymentDate = self.paymentDate

        # If a file is attached, ensure that it is not public, and that it is saved in the 'Expense Receipts' folder
        if self.attachment:
            try:
                self.attachment.folder = Folder.objects.get(name=_('Expense Receipts'))
            except ObjectDoesNotExist:
                pass
            self.attachment.is_public = False
            self.attachment.save()

    def __str__(self):
        if self.accrualDate:
            return '%s %s: %s = %s%s' % (self.category.name, self.accrualDate.strftime('%B %Y'),self.description, getConstant('general__currencySymbol'), self.total)
        else:
            return '%s: %s = %s%s' % (self.category.name, self.description, getConstant('general__currencySymbol'), self.total)

    def __init__(self, *args, **kwargs):
        '''
        Permit easy checking to determine if the object
        already exists and has changed on saving
        '''
        super(self.__class__, self).__init__(*args, **kwargs)
        self.__approved = self.approved
        self.__paid = self.paid
        self.__approvalDate = self.approvalDate
        self.__paymentDate = self.paymentDate

    class Meta:
        ordering = ['-accrualDate',]
        verbose_name = _('Expense item')
        verbose_name_plural = _('Expense items')

        permissions = (
            ('mark_expenses_paid',_('Mark expenses as paid at the time of submission')),
        )


@python_2_unicode_compatible
class RevenueCategory(models.Model):
    '''
    These are the different available categories of payment
    '''

    name = models.CharField(_('Name'),max_length=50,unique=True,help_text=_('Different types of revenue fall under different categories.'))
    defaultAmount = models.FloatField(_('Default amount'),help_text=_('This is the default amount of revenue for items in this category.'),null=True,blank=True,validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Revenue category')
        verbose_name_plural = _('Revenue categories')


@python_2_unicode_compatible
class RevenueItem(models.Model):
    '''
    All revenue-producing transactions (e.g. class payments, other payments) should have an associated RevenueItem
    '''

    submissionUser = models.ForeignKey(User,null=True,blank=True,related_name='revenuessubmittedby',verbose_name=_('Submission user'))
    submissionDate = models.DateTimeField(_('Submission date'),auto_now_add=True)

    category = models.ForeignKey(RevenueCategory,verbose_name=_('Category'))
    description = models.CharField(_('Description'),max_length=200,null=True,blank=True)
    total = models.FloatField(_('Total'),help_text=_('The total revenue received, net of any discounts or voucher uses.  This is what we actually receive.'),validators=[MinValueValidator(0)])
    grossTotal = models.FloatField(_('Gross Total'),help_text=_('The gross total billed before the application of any discounts, or the use of any vouchers.'),validators=[MinValueValidator(0)])
    adjustments = models.FloatField(_('Adjustments'),help_text=_('Record any ex-post adjustments to the amount (e.g. refunds) in this field.  A positive amount increases the netRevenue, a negative amount reduces the netRevenue.'),default=0)
    fees = models.FloatField(_('Fees'),help_text=_('The sum of any transaction fees (e.g. Paypal fees) that were paid <strong>by us</strong>, and should therefore be subtracted from net revenue.'),default=0)
    taxes = models.FloatField(_('Taxes'),default=0)

    paymentMethod = models.CharField(_('Payment method'),max_length=50,null=True,blank=True)
    invoiceNumber = models.CharField(_('Invoice Number'),help_text=_('For Paypal payments, this will be the txn_id.  For cash payments, this will be automatically generated by the submission form.  More than one revenue item may have the same invoice number, because multiple events are paid for in one Paypal transaction.'),null=True,blank=True,max_length=80)

    comments = models.TextField(_('Comments/Notes'),null=True,blank=True)
    attachment = FilerFileField(verbose_name=_('Attach File (optional)'),null=True,blank=True,related_name='revenue_attachment')

    # With the invoice system in the core app, Revenue Items need only link with Invoice Items
    invoiceItem = models.OneToOneField(InvoiceItem,null=True, blank=True,verbose_name=_('Associated invoice item'))

    event = models.ForeignKey(Event,null=True,blank=True,verbose_name=_('Event'),help_text=_('If this item is associated with an Event, enter it here.'))
    receivedFromName = models.CharField(_('Received From'),max_length=50,null=True,blank=True,help_text=_('Enter who this revenue item was received from, if it is not associated with an existing registration.'))

    currentlyHeldBy = models.ForeignKey(User,null=True,blank=True,verbose_name=_('Cash currently in possession of'),help_text=_('If cash has not yet been deposited, this indicates who to contact in order to collect the cash for deposit.'),related_name='revenuesheldby')
    received = models.BooleanField(_('Received'),help_text=_('Check to indicate that payment has been received. Non-received payments are considered pending.'),default=False)
    receivedDate = models.DateTimeField(_('Date received'),null=True,blank=True)

    # This field is used to aggregate expenses over time (e.g. by month).
    # The value of this field is auto-updated using pre-save methods. If
    # there is a registration or an event associated with this expense,
    # then the value is taken from that.  Otherwise, the submission date
    # is used.
    accrualDate = models.DateTimeField(_('Accrual date'))

    @property
    def relatedItems(self):
        '''
        If this item is associated with a registration, then return all other items associated with
        the same registration.
        '''
        if self.registration:
            return self.registration.revenueitem_set.exclude(pk=self.pk)
    relatedItems.fget.short_description = _('Related items')

    @property
    def netRevenue(self):
        return self.total + self.adjustments - self.fees
    netRevenue.fget.short_description = _('Net revenue')

    def save(self, *args, **kwargs):
        '''
        This custom save method ensures that a revenue item is not attributed to multiple categories.
        It also ensures that the series and event properties are always associated with any
        type of revenue of that series or event.
        '''

        # Set the received date if the payment was just marked received
        if not hasattr(self,'__received'):
            if self.received and not self.receivedDate:
                self.receivedDate = timezone.now()
        else:
            if self.received and not self.receivedDate and not self.__receivedDate:
                self.receivedDate = timezone.now()

        # Set the accrual date.  The method for series/events ensures that the accrualDate month
        # is the same as the reported month of the event/series by accruing to the start date of the first
        # occurrence in that month.
        if not self.accrualDate:
            if self.invoiceItem and self.invoiceItem.finalEventRegistration:
                min_event_time = self.invoiceItem.finalEventRegistration.event.eventoccurrence_set.filter(**{'startTime__month':self.invoiceItem.finalEventRegistration.event.month}).first().startTime
                self.accrualDate = min_event_time
            elif self.event:
                self.accrualDate = self.event.eventoccurrence_set.order_by('startTime').filter(**{'startTime__month': self.event.month}).last().startTime
            elif self.invoiceItem:
                self.accrualDate = self.invoiceItem.invoice.creationDate
            elif self.receivedDate:
                self.accrualDate = self.receivedDate
            else:
                self.accrualDate = self.submissionDate

        # Now, set the registration property and check that this item is not attributed
        # to multiple categories.
        if self.invoiceItem and self.invoiceItem.finalEventRegistration:
            self.event = self.invoiceItem.finalEventRegistration.event
        elif self.invoiceItem and self.invoiceItem.temporaryEventRegistration:
            self.event = self.invoiceItem.temporaryEventRegistration.event

        # If no grossTotal is reported, use the net total.  If no net total is reported, use the grossTotal
        if self.grossTotal is None and self.total:
            self.grossTotal = self.total
        if self.total is None and self.grossTotal:
            self.total = self.grossTotal

        super(RevenueItem, self).save(*args, **kwargs)
        self.__received = self.received
        self.__receivedDate = self.receivedDate

        # If a file is attached, ensure that it is not public, and that it is saved in the 'Expense Receipts' folder
        if self.attachment:
            try:
                self.attachment.folder = Folder.objects.get(name=_('Revenue Receipts'))
            except ObjectDoesNotExist:
                pass
            self.attachment.is_public = False
            self.attachment.save()

    def __str__(self):
        if self.accrualDate:
            return '%s %s: %s = %s%s' % (self.category.name, self.accrualDate.strftime('%B %Y'),self.description, getConstant('general__currencySymbol'), self.total)
        else:
            return '%s: %s = %s%s' % (self.category.name, self.description, getConstant('general__currencySymbol'), self.total)

    def __init__(self,*args,**kwargs):
        '''
        Permit easy checking to determine if the object
        already exists and has changed on saving
        '''
        super(self.__class__, self).__init__(*args, **kwargs)
        self.__received = self.received
        self.__receivedDate = self.receivedDate

    class Meta:
        ordering = ['-accrualDate',]
        verbose_name = _('Revenue item')
        verbose_name_plural = _('Revenue items')

        permissions = (
            ('export_financial_data',_('Export detailed financial transaction information to CSV')),
            ('view_finances_bymonth',_('View school finances month-by-month')),
            ('view_finances_byevent',_('View school finances by Event')),
            ('view_finances_detail',_('View school finances as detailed statement')),
        )
