from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from polymorphic.models import PolymorphicModel
from filer.fields.file import FilerFileField
from filer.models import Folder
import math
from djchoices import DjangoChoices, ChoiceItem
from calendar import day_name
from datetime import time, timedelta
from dateutil.relativedelta import relativedelta
from intervaltree import IntervalTree

from danceschool.core.models import StaffMember, EventStaffCategory, Event, InvoiceItem, Location, Room
from danceschool.core.constants import getConstant


def ordinal(n):
    ''' This is just used to populate ordinal day of the month choices '''
    return "%d%s" % (n,"tsnrhtdd"[(math.floor(n / 10) % 10 != 1) * (n % 10 < 4) * n % 10::4])


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


class RepeatedExpenseRule(PolymorphicModel):
    '''
    This base class defines the pieces of information
    needed for any type of repeated expense creation, such
    as daily/weekly/monthly expense generation for venues
    and instructors, as well as generic repeated expenses.
    '''

    class RateRuleChoices(DjangoChoices):
        hourly = ChoiceItem('H',_('Per hour'))
        daily = ChoiceItem('D',_('Per day of scheduled events'))
        weekly = ChoiceItem('W',_('Per week'))
        monthly = ChoiceItem('M',_('Per month'))

    class MilestoneChoices(DjangoChoices):
        start = ChoiceItem('S',_('First occurrence starts'))
        end = ChoiceItem('E',_('Last occurrence ends'))

    rentalRate = models.FloatField(
        _('Expense Rate'),validators=[MinValueValidator(0)],help_text=_('In default currency')
    )

    applyRateRule = models.CharField(
        _('Apply this rate'),
        max_length=1,
        choices=RateRuleChoices.choices,
        default=RateRuleChoices.hourly,
    )

    dayStarts = models.PositiveSmallIntegerField(
        _('Day starts at'),
        choices=[(i, time(i).strftime('%-I:00 %p')) for i in range(24)],
        default=0,
        validators=[MinValueValidator(0),MaxValueValidator(23)],
        help_text=_('If you run events after midnight, avoids creation of duplicate expense items'),
    )

    weekStarts = models.PositiveSmallIntegerField(
        _('Week starts on'),
        choices=[(x,day_name[x]) for x in range(0,7)],
        default=0,
        validators=[MinValueValidator(0),MaxValueValidator(6)]
    )

    monthStarts = models.PositiveSmallIntegerField(
        _('Month starts on'),
        choices=[(x, ordinal(x)) for x in range(1,29)],
        default=1,
        validators=[MinValueValidator(1),MaxValueValidator(28)]
    )

    startDate = models.DateField(
        _('Start date'),
        null=True,
        blank=True,
        help_text=_('If specified, then expense items will not be generated prior to this date.')
    )

    endDate = models.DateField(
        _('End date'),
        null=True,
        blank=True,
        help_text=_('If specified, then expense items will not be generated after this date.  Leave blank for expenses to be generated indefinitely.')
    )

    advanceDays = models.PositiveSmallIntegerField(
        _('Generate expenses up to __ days in advance'),
        default=30,
    )

    advanceDaysReference = models.CharField(
        _('in advance of'),
        max_length=1,
        choices=MilestoneChoices.choices,
        default=MilestoneChoices.start,
    )

    priorDays = models.PositiveSmallIntegerField(
        _('Generate expenses up to __ days in the past'),
        help_text=_('Leave blank for no limit.'),
        default=180,
        null=True,
        blank=True
    )

    priorDaysReference = models.CharField(
        _('prior to'),
        max_length=1,
        choices=MilestoneChoices.choices,
        default=MilestoneChoices.end,
    )

    disabled = models.BooleanField(
        _('Disable autogeneration of expenses under this rule'),
        default=False,
        help_text=_(
            'It is recommended to disable expense rules rather than delete them for ' +
            'temporary purposes, to avoid the creation of duplicate expense items.'
        ),
    )

    lastRun = models.DateTimeField(_('Last run time'),null=True,blank=True)

    def generateExpenses(self,request=None,datetimeTuple=None):
        '''
        Child classes that define this method can have their expense rule run
        from the admin interface.
        '''
        pass

    def timeAtThreshold(self,dateTime):
        '''
        A convenience method for checking when a time is on the start/end boundary
        for this rule.
        '''

        # Anything that's not at a day boundary is for sure not at a threshold.
        if not (
            dateTime.hour == self.dayStarts and dateTime.minute == 0 and
            dateTime.second == 0 and dateTime.microsecond == 0
        ):
            return False

        if self.applyRateRule == self.RateRuleChoices.daily:
            return True
        elif self.applyRateRule == self.RateRuleChoices.weekly:
            return (dateTime == self.weekStarts)
        elif self.applyRateRule == self.RateRuleChoices.monthly:
            return (dateTime.day == self.monthStarts)

        # Everything else is nonsensical, so False.
        return False

    def getWindowsAndTotals(self,intervals):

        # Ensure that the intervals are passed with startTime and endTime in order, and reduce
        # the intervals down to non-overlapping intervals.
        intervals = [sorted(x) for x in intervals]
        tree = IntervalTree.from_tuples(intervals)
        tree.merge_overlaps()

        # This is the set of times at which weekly or monthly intervals need to be sliced
        # (i.e. the start of each new week or month period).
        slice_times = set()

        # Using the set of passed intervals, construct the set of day,
        # week, or monthly intervals specified by the expense rule.
        for startTime, endTime in [(x.begin, x.end) for x in tree]:

            if self.applyRateRule == self.RateRuleChoices.daily:
                # Period is the date or dates of the occurrence
                this_window_start = startTime.replace(hour=self.dayStarts,minute=0,second=0,microsecond=0)
                this_window_end = (endTime + timedelta(days=1)).replace(hour=self.dayStarts,minute=0,second=0,microsecond=0) \
                    if not self.timeAtThreshold(endTime) else endTime
            elif self.applyRateRule == self.RateRuleChoices.weekly:
                # Period is the week of the occurrence, starting from the start date specified for
                # the Location.
                if startTime.weekday() > self.weekStarts:
                    start_offset = self.weekStarts - startTime.weekday()
                else:
                    start_offset = self.weekStarts - startTime.weekday() - 7

                if endTime.weekday() > self.weekStarts or (endTime.weekday() == self.weekStarts and not self.timeAtThreshold(endTime)):
                    end_offset = 7 + self.weekStarts - endTime.weekday()
                else:
                    end_offset = self.weekStarts - endTime.weekday()

                this_window_start = (startTime + timedelta(days=start_offset)).replace(hour=self.dayStarts, minute=0, second=0, microsecond=0)
                this_window_end = (endTime + timedelta(days=end_offset)).replace(hour=self.dayStarts, minute=0, second=0, microsecond=0)

                # Add the weekly slice times to the set
                t0 = this_window_start
                while t0 <= this_window_end:
                    slice_times.add(t0)
                    t0 = t0 + timedelta(days=7)

            elif self.applyRateRule == self.RateRuleChoices.monthly:
                # Period is the month of the occurrence, starting from the start date specified for
                # the Location.
                startDay = self.monthStarts

                if startTime.day >= startDay:
                    this_window_start = startTime.replace(day=startDay,hour=self.dayStarts,minute=0,second=0,microsecond=0)
                else:
                    this_window_start = (startTime + relativedelta(months=-1)).replace(day=startDay,hour=self.dayStarts,minute=0,second=0,microsecond=0)
                if endTime.day > startDay or (endTime.day == startDay and not self.timeAtThreshold(endTime)):
                    this_window_end = (endTime + relativedelta(months=1)).replace(day=startDay,hour=self.dayStarts,minute=0,second=0,microsecond=0)
                else:
                    this_window_end = endTime.replace(day=startDay,hour=self.dayStarts,minute=0,second=0,microsecond=0)

                # Add the monthly slice times to the set
                t0 = this_window_start
                while t0 <= this_window_end:
                    slice_times.add(t0)
                    t0 = t0 + relativedelta(months=1)

            # Add the newly constructed interval to the tree of intervals
            tree.addi(this_window_start, this_window_end)

        # Remove all overlapping intervals and also chop out any intervals for which there is already an
        # expense item existing.  (we will split again by week or month afterward.)
        tree.merge_overlaps()

        startTime = tree.begin()
        endTime = tree.end()

        overlapping = self.expenseitem_set.filter(
            (models.Q(periodStart__lte=endTime) & models.Q(periodStart__gte=startTime)) |
            (models.Q(periodEnd__gte=startTime) & models.Q(periodEnd__lte=endTime)) |
            (models.Q(periodStart__lte=startTime) & models.Q(periodEnd__gte=endTime))
        )

        for item in overlapping:
            tree.chop(item.periodStart, item.periodEnd)

        # Now merge the intervals again, and split at the split times if needed
        tree.merge_overlaps()
        for slice_time in slice_times:
            tree.slice(slice_time)

        # Now, loop through the items of the finalized tree and yield the times,
        # a description and total expense for the interval allocated by the fraction
        # of a full week/month interval contained in the interval so that new
        # ExpenseItems may be created.
        for startTime, endTime in [(x.begin, x.end) for x in tree]:

            # Default description is overridden below as appropriate
            description = str(_('%(start)s to %(end)s' % {
                'start': startTime.strftime('%Y-%m-%d'),
                'end': (endTime - timedelta(hours=self.dayStarts,minutes=1)).strftime('%Y-%m-%d')
            }))

            if self.applyRateRule == self.RateRuleChoices.daily:
                num_days = (endTime - startTime).days
                total = self.rentalRate * num_days

                if num_days == 1:
                    description = startTime.strftime('%Y-%m-%d')

            elif self.applyRateRule == self.RateRuleChoices.weekly:
                num_days = (endTime - startTime).days
                total = self.rentalRate * (num_days / 7)

                if num_days == 7:
                    description = str(_('week of %(start)s to %(end)s' % {
                        'start': startTime.strftime('%Y-%m-%d'),
                        'end': (endTime - timedelta(hours=self.dayStarts,minutes=1)).strftime('%Y-%m-%d')
                    }))

            elif self.applyRateRule == self.RateRuleChoices.monthly:
                num_days = (endTime - startTime).days

                # We need to know the number days in the month in order to allocate partial expenses
                month_startDate = startTime.replace(day=startDay,hour=self.dayStarts,minute=0,second=0,microsecond=0)
                month_startDate = month_startDate - relativedelta(months=1) if month_startDate > startTime else month_startDate
                days_in_month = (month_startDate + relativedelta(months=1) - month_startDate).days
                total = self.rentalRate * (num_days / days_in_month)

                if num_days == days_in_month:
                    description = str(_('month of %(start)s to %(end)s' % {
                        'start': startTime.strftime('%Y-%m-%d'),
                        'end': (endTime - timedelta(hours=self.dayStarts,minutes=1)).strftime('%Y-%m-%d')
                    }))

            # Yield the information for this interval
            yield (startTime, endTime, total, description)

    @property
    def ruleName(self):
        ''' This should be overridden for child classes '''
        return '%s %s' % (self.rentalRate, self.RateRuleChoices.values.get(self.applyRateRule,self.applyRateRule))
    ruleName.fget.short_description = _('Rule name')

    def __str__(self):
        ''' Should be overridden by child classes with something more descriptive. '''
        return str(_('Repeated expense rule: %s' % self.name))


class LocationRentalInfo(RepeatedExpenseRule):
    '''
    This model is used to store information on rental periods and rates
    for locations.
    '''
    location = models.OneToOneField(Location,related_name='rentalinfo',verbose_name=_('Location'))

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return self.location.name
    ruleName.fget.short_description = _('Rule name')

    def generateExpenses(self,request=None,datetimeTuple=None):
        from .helpers import createExpenseItemsForVenueRental
        return createExpenseItemsForVenueRental(rule=self,request=request,datetimeTuple=datetimeTuple)

    def __str__(self):
        return str(_('Rental expense information for: %s' % self.location.name))

    class Meta:
        verbose_name = _('Location rental information')
        verbose_name_plural = _('Locations\' rental information')


class RoomRentalInfo(RepeatedExpenseRule):
    '''
    This model is used to store information on rental periods and rates
    for individual rooms.  If a rental rate does not exist for a room,
    or if it is specified that the room rental rate not be applied,
    then the location's rental rate and parameters are used instead.
    '''
    room = models.OneToOneField(Room,related_name='rentalinfo',verbose_name=_('Room'))

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return _('%s at %s' % (self.room.name, self.room.location.name))
    ruleName.fget.short_description = _('Rule name')

    def generateExpenses(self,request=None,datetimeTuple=None):
        from .helpers import createExpenseItemsForVenueRental
        return createExpenseItemsForVenueRental(rule=self,request=request,datetimeTuple=datetimeTuple)

    def __str__(self):
        return str(_('Rental expense information for: %s at %s' % (self.room.name, self.room.location.name)))

    class Meta:
        verbose_name = _('Room rental information')
        verbose_name_plural = _('Rooms\' rental information')


class StaffMemberWageInfo(RepeatedExpenseRule):
    '''
    This model is used to store information on rental periods and rates
    for individual rooms.  If a rental rate does not exist for a room,
    or if it is specified that the room rental rate not be applied,
    then the location's rental rate and parameters are used instead.
    '''
    staffMember = models.ForeignKey(StaffMember,related_name='expenserules',verbose_name=_('Staff member'))
    category = models.ForeignKey(
        EventStaffCategory,
        verbose_name=_('Category'),
        null=True,blank=True,
        help_text=_('If left blank, then this expense rule will be used for all categories.  If a category-specific rate is specified, then that will be used instead.  If nothing is specified for an instructor, then the default hourly rate for each category will be used.'),
        on_delete=models.SET_NULL,
    )

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return _('%s: %s' % (self.staffMember.fullName, self.category or 'All unspecified categories'))
    ruleName.fget.short_description = _('Rule name')

    def generateExpenses(self,request=None,datetimeTuple=None):
        from .helpers import createExpenseItemsForEvents
        return createExpenseItemsForEvents(rule=self,request=request,datetimeTuple=datetimeTuple)

    def __str__(self):
        return str(_('%s wage/salary information for: %s' % (self.category or 'Rental', self.staffMember.fullName)))

    class Meta:
        unique_together = ('staffMember', 'category')
        ordering = ('staffMember','category__name')
        verbose_name = _('Staff member salary information')
        verbose_name_plural = _('Staff members\' wage/salary information')


class GenericRepeatedExpense(RepeatedExpenseRule):
    '''
    This model is used to store repeated expenses that are not specifically tied to location
    rental or event staffing.  That is, expenses are generated under these rules regardless
    of whether any series or events are booked.
    '''

    name = models.CharField(_('Give this expense generation rule a name'),max_length=100,unique=True)

    category = models.ForeignKey(ExpenseCategory,verbose_name=_('Category'),null=True,on_delete=models.SET_NULL,)

    # An expense can be directly associated with a user (like an instructor) or
    # a location, or the name of another party can be entered.
    payToUser = models.ForeignKey(
        User,null=True,blank=True,
        verbose_name=_('Pay to user'),on_delete=models.SET_NULL,)
    payToLocation = models.ForeignKey(Location,null=True,blank=True,verbose_name=_('Pay to location'))
    payToName = models.CharField(_('Pay to (enter name)'),max_length=50, null=True,blank=True)

    markApproved = models.BooleanField(_('Automatically mark this expense as approved'),default=False)
    markPaid = models.BooleanField(_('Automatically mark this expense as paid'),default=False)
    paymentMethod = models.CharField(
        _('Payment method'),
        max_length=50,null=True,blank=True,
        help_text=_('This field is ignored unless you have chosen to automatically mark expenses as paid.')
    )

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return self.name
    ruleName.fget.short_description = _('Rule name')

    def clean(self):
        ''' priorDays is required for Generic Repeated Expenses to avoid infinite loops '''
        if not self.priorDays and not self.startDate:
            raise ValidationError(_(
                'Either a start date or an "up to __ days in the past" limit is required ' +
                'for repeated expense rules that are not associated with a venue or a staff member.'
            ))
        super(GenericRepeatedExpense,self).clean()

    def generateExpenses(self,request=None,datetimeTuple=None):
        from .helpers import createGenericExpenseItems
        return createGenericExpenseItems(rule=self,request=request,datetimeTuple=datetimeTuple)

    def __str__(self):
        return str(_('Repeated expense rule: %s' % self.name))

    class Meta:
        ordering = ('name',)
        verbose_name = _('Other repeated expense')
        verbose_name_plural = _('Other repeated expenses')


class ExpenseItem(models.Model):
    '''
    Expenses may be associated with EventStaff or with Events, or they may be associated with nothing
    '''

    submissionUser = models.ForeignKey(
        User,
        verbose_name=_('Submission user'),
        related_name='expensessubmittedby',
        null=True,blank=True,on_delete=models.SET_NULL,)
    submissionDate = models.DateTimeField(_('Submission date'),auto_now_add=True)

    category = models.ForeignKey(ExpenseCategory,verbose_name=_('Category'),null=True,on_delete=models.SET_NULL,)

    description = models.CharField(_('Description'),max_length=200,null=True,blank=True)

    hours = models.FloatField(
        _('Hours'),
        help_text=_('Please indicate the number of hours to be paid for.'),
        null=True,blank=True,validators=[MinValueValidator(0)])
    wageRate = models.FloatField(
        _('Wage rate'),
        help_text=_('This should be filled automatically, but can be changed as needed.'),
        null=True,blank=True,validators=[MinValueValidator(0)])
    total = models.FloatField(_('Total amount'),null=True,blank=True,validators=[MinValueValidator(0)])
    adjustments = models.FloatField(
        _('Adjustments/refunds'),
        help_text=_('Record any ex-post adjustments to the amount (e.g. refunds) in this field. A positive amount increases the netExpense, a negative amount reduces the netExpense.'),
        default=0)
    fees = models.FloatField(
        _('Fees'),
        help_text=_('The sum of any transaction fees (e.g. Paypal fees) that were paid <strong>by us</strong>, and should therefore be added to net expense.'),
        default=0)

    paymentMethod = models.CharField(_('Payment method'),max_length=50,null=True,blank=True)

    comments = models.TextField(_('Comments/Notes'),null=True,blank=True)
    attachment = FilerFileField(verbose_name=_('Attach File (optional)'),null=True,blank=True,related_name='expense_attachment')

    # An expense item will automatically be associated with an event if it is an automatically-generated
    # _hourly_ expense for venue rental or for event staff.  This facilitates event-level financial statements.
    # Non-hourly generated expense items are not automatically affiliated with events.  It is also possible
    # to affiliate an Expense Item with an event via the Expense Reporting Form.
    event = models.ForeignKey(
        Event,
        null=True,blank=True,
        verbose_name=_('Event'),
        help_text=_('If this item is associated with an Event, enter it here.'),on_delete=models.SET_NULL,)

    # For periodic expenses (e.g. hourly/daily/weekly/monthly venue rental, instructor expenses, etc.  This foreign key
    # also replaces the prior relations eventstaffmember and eventvenue, because all automatically generated expenses
    # are now generated against specific repeated expense rules.
    expenseRule = models.ForeignKey(
        RepeatedExpenseRule,
        verbose_name=_('Expense generation rule'),
        null=True,blank=True,on_delete=models.SET_NULL,)

    # For daily/weekly/monthly automatically-generate expenses, this defines the period over which
    # this expense item applies.
    periodStart = models.DateTimeField(_('Expense period start'),null=True,blank=True)
    periodEnd = models.DateTimeField(_('Expense period end'),null=True,blank=True)

    # An expense can be directly associated with a user (like an instructor) or
    # a location, or the name of another party can be entered.
    payToUser = models.ForeignKey(
        User,null=True,blank=True,
        related_name='payToUser',verbose_name=_('Pay to user'),on_delete=models.SET_NULL,)
    payToLocation = models.ForeignKey(Location,null=True,blank=True,verbose_name=_('Pay to location'))
    payToName = models.CharField(_('Pay to (enter name)'),max_length=50, null=True,blank=True)

    reimbursement = models.BooleanField(
        _('Reimbursement'),
        help_text=_('Check to indicate that this is a reimbursement expense (i.e. not compensation).'),
        default=False)

    approved = models.BooleanField(
        _('Approved'),
        help_text=_('Check to indicate that expense is approved for payment.'),
        default=False)
    paid = models.BooleanField(
        _('Paid'),
        help_text=_('Check to indicate that payment has been made.'),
        default=False)

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
    def expenseStartDate(self):
        theTime = self.accrualDate
        if self.periodStart:
            theTime = self.periodStart
        elif self.event:
            theTime = self.event.startTime
        return theTime
    expenseStartDate.fget.short_description = _('Start Date')

    @property
    def expenseEndDate(self):
        theTime = self.accrualDate
        if self.periodEnd:
            theTime = self.periodEnd
        elif self.event:
            theTime = self.event.endTime
        return theTime
    expenseEndDate.fget.short_description = _('End Date')

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

        # Fill out the series and event properties to permit easy calculation of
        # revenues and expenses by series or by event.
        if (
            self.expenseRule and hasattr(self.expenseRule,'staffMember') and
            hasattr(self.expenseRule.staffMember,'userAccount') and not self.payToUser
        ):
            self.payToUser = self.expenseRule.staffMember.userAccount
        if (
            self.expenseRule and hasattr(self.expenseRule,'location') and
            not self.payToLocation
        ):
            self.payToLocation = self.expenseRule.location

        # Set the accrual date.  The method for events ensures that the accrualDate month
        # is the same as the reported month of the series/event by accruing to the end date of the last
        # class or occurrence in that month.
        if not self.accrualDate:
            if self.event and self.event.month:
                self.accrualDate = self.event.eventoccurrence_set.order_by('endTime').filter(**{'endTime__month': self.event.month}).last().endTime
            elif self.submissionDate:
                self.accrualDate = self.submissionDate
            else:
                self.submissionDate = timezone.now()
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


class RevenueItem(models.Model):
    '''
    All revenue-producing transactions (e.g. class payments, other payments) should have an associated RevenueItem
    '''

    submissionUser = models.ForeignKey(
        User,null=True,blank=True,related_name='revenuessubmittedby',
        verbose_name=_('Submission user'),on_delete=models.SET_NULL,)
    submissionDate = models.DateTimeField(_('Submission date'),auto_now_add=True)

    category = models.ForeignKey(RevenueCategory,verbose_name=_('Category'),null=True,on_delete=models.SET_NULL,)
    description = models.CharField(_('Description'),max_length=200,null=True,blank=True)
    total = models.FloatField(_('Total'),help_text=_('The total revenue received, net of any discounts or voucher uses.  This is what we actually receive.'),validators=[MinValueValidator(0)])
    grossTotal = models.FloatField(_('Gross Total'),help_text=_('The gross total billed before the application of any discounts, or the use of any vouchers.'),validators=[MinValueValidator(0)])
    adjustments = models.FloatField(_('Adjustments'),help_text=_('Record any ex-post adjustments to the amount (e.g. refunds) in this field.  A positive amount increases the netRevenue, a negative amount reduces the netRevenue.'),default=0)
    fees = models.FloatField(_('Fees'),help_text=_('The sum of any transaction fees (e.g. Paypal fees) that were paid <strong>by us</strong>, and should therefore be subtracted from net revenue.'),default=0)
    taxes = models.FloatField(_('Taxes'),default=0)
    buyerPaysSalesTax = models.BooleanField(_('Buyer pays sales tax'), default=False)

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
        net = self.total + self.adjustments - self.fees
        if not self.buyerPaysSalesTax:
            net -= self.taxes
        return net
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
            elif self.submissionDate:
                self.accrualDate = self.submissionDate
            else:
                self.submissionDate = timezone.now()
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
