import math
from calendar import day_name
from datetime import time, timedelta

from dateutil.relativedelta import relativedelta
from intervaltree import IntervalTree

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _

from polymorphic.models import PolymorphicModel

from danceschool.core.models import EventStaffCategory, Location, Room, StaffMember

from .parties import TransactionParty


def ordinal(n):
    ''' This is just used to populate ordinal day of the month choices '''
    return "%d%s" % (n, "tsnrhtdd"[(math.floor(n / 10) % 10 != 1) * (n % 10 < 4) * n % 10::4])


class RepeatedExpenseRule(PolymorphicModel):
    '''
    This base class defines the pieces of information
    needed for any type of repeated expense creation, such
    as daily/weekly/monthly expense generation for venues
    and instructors, as well as generic repeated expenses.
    '''

    class RateRuleChoices(models.TextChoices):
        hourly = ('H', _('Per hour'))
        daily = ('D', _('Per day of scheduled events'))
        weekly = ('W', _('Per week'))
        monthly = ('M', _('Per month'))

    class MilestoneChoices(models.TextChoices):
        start = ('S', _('First occurrence starts'))
        end = ('E', _('Last occurrence ends'))

    rentalRate = models.FloatField(
        _('Expense Rate'), validators=[MinValueValidator(0)], help_text=_('In default currency')
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
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text=_('If you run events after midnight, avoids creation of duplicate expense items'),
    )

    weekStarts = models.PositiveSmallIntegerField(
        _('Week starts on'),
        choices=[(x, day_name[x]) for x in range(0, 7)],
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(6)]
    )

    monthStarts = models.PositiveSmallIntegerField(
        _('Month starts on'),
        choices=[(x, ordinal(x)) for x in range(1, 29)],
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(28)]
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
        help_text=_(
            'If specified, then expense items will not be generated after ' +
            'this date.  Leave blank for expenses to be generated indefinitely.'
        )
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

    lastRun = models.DateTimeField(_('Last run time'), null=True, blank=True)

    def generateExpenses(self, request=None, datetimeTuple=None):
        '''
        Child classes that define this method can have their expense rule run
        from the admin interface.
        '''
        pass

    def timeAtThreshold(self, dateTime):
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

    def getWindowsAndTotals(
        self, intervals, remove_existing_overlaps=False, category=None, payTo=None
    ):
        # Lazy import to avoid circular dependency with expenses.py
        from .expenses import ExpenseItem

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
                this_window_start = startTime.replace(
                    hour=self.dayStarts, minute=0, second=0, microsecond=0
                )
                this_window_end = (
                    (endTime + timedelta(days=1)).replace(
                        hour=self.dayStarts, minute=0, second=0, microsecond=0
                    )
                    if not self.timeAtThreshold(endTime) else endTime
                )
            elif self.applyRateRule == self.RateRuleChoices.weekly:
                # Period is the week of the occurrence, starting from the start
                # date specified for the Location.
                if startTime.weekday() > self.weekStarts:
                    start_offset = self.weekStarts - startTime.weekday()
                else:
                    start_offset = self.weekStarts - startTime.weekday() - 7

                if (
                    endTime.weekday() > self.weekStarts or
                    (endTime.weekday() == self.weekStarts and not self.timeAtThreshold(endTime))
                ):
                    end_offset = 7 + self.weekStarts - endTime.weekday()
                else:
                    end_offset = self.weekStarts - endTime.weekday()

                this_window_start = (startTime + timedelta(days=start_offset)).replace(
                    hour=self.dayStarts, minute=0, second=0, microsecond=0
                )
                this_window_end = (endTime + timedelta(days=end_offset)).replace(
                    hour=self.dayStarts, minute=0, second=0, microsecond=0
                )

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
                    this_window_start = startTime.replace(
                        day=startDay, hour=self.dayStarts, minute=0, second=0, microsecond=0
                    )
                else:
                    this_window_start = (startTime + relativedelta(months=-1)).replace(
                        day=startDay, hour=self.dayStarts, minute=0, second=0, microsecond=0
                    )
                if (
                    endTime.day > startDay or
                    (endTime.day == startDay and not self.timeAtThreshold(endTime))
                ):
                    this_window_end = (endTime + relativedelta(months=1)).replace(
                        day=startDay, hour=self.dayStarts, minute=0, second=0, microsecond=0
                    )
                else:
                    this_window_end = endTime.replace(
                        day=startDay, hour=self.dayStarts, minute=0, second=0, microsecond=0
                    )

                # Add the monthly slice times to the set
                t0 = this_window_start
                while t0 <= this_window_end:
                    slice_times.add(t0)
                    t0 = t0 + relativedelta(months=1)

            # Add the newly constructed interval to the tree of intervals
            tree.addi(this_window_start, this_window_end)

        # Remove all overlapping intervals and also chop out any intervals for
        # which there is already an expense item existing.  (we will split again
        # by week or month afterward.)
        tree.merge_overlaps()

        startTime = tree.begin()
        endTime = tree.end()

        if remove_existing_overlaps:
            if startTime and endTime and self.pk:
                overlapping = self.expenseitem_set.filter(
                    (Q(periodStart__lte=endTime) & Q(periodStart__gte=startTime)) |
                    (Q(periodEnd__gte=startTime) & Q(periodEnd__lte=endTime)) |
                    (Q(periodStart__lte=startTime) & Q(periodEnd__gte=endTime))
                )
                if category:
                    overlapping = overlapping.filter(category=category)
                if payTo:
                    overlapping = overlapping.filter(payTo=payTo)
            else:
                overlapping = ExpenseItem.objects.none()

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
                'end': (endTime - timedelta(hours=self.dayStarts, minutes=1)).strftime('%Y-%m-%d')
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
                        'end': (endTime - timedelta(hours=self.dayStarts, minutes=1)).strftime('%Y-%m-%d')
                    }))

            elif self.applyRateRule == self.RateRuleChoices.monthly:
                num_days = (endTime - startTime).days

                # We need to know the number days in the month in order to allocate partial expenses
                month_startDate = startTime.replace(
                    day=startDay, hour=self.dayStarts, minute=0, second=0, microsecond=0
                )
                month_startDate = (
                    month_startDate - relativedelta(months=1) if
                    month_startDate > startTime else month_startDate
                )
                days_in_month = (month_startDate + relativedelta(months=1) - month_startDate).days
                total = self.rentalRate * (num_days / days_in_month)

                if num_days == days_in_month:
                    description = str(_('month of %(start)s to %(end)s' % {
                        'start': startTime.strftime('%Y-%m-%d'),
                        'end': (endTime - timedelta(hours=self.dayStarts, minutes=1)).strftime('%Y-%m-%d')
                    }))

            # Yield the information for this interval
            yield (startTime, endTime, total, description)

    @property
    def ruleName(self):
        ''' This should be overridden for child classes '''
        return '%s %s' % (
            self.rentalRate,
            self.get_applyRateRule_display(),
        )
    ruleName.fget.short_description = _('Rule name')

    def __str__(self):
        ''' Should be overridden by child classes with something more descriptive. '''
        return str(_('Repeated expense rule: %s' % self.ruleName))

    class Meta:
        verbose_name = _('Repeated expense rule')
        verbose_name_plural = _('Repeated expense rules')

        permissions = (
            (
                'can_generate_repeated_expenses',
                _('Able to generate rule-based repeated expenses using the admin view')
            ),
        )


class LocationRentalInfo(RepeatedExpenseRule):
    '''
    This model is used to store information on rental periods and rates
    for locations.
    '''
    location = models.OneToOneField(
        Location, related_name='rentalinfo', verbose_name=_('Location'),
        on_delete=models.CASCADE,
    )

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return self.location.name
    ruleName.fget.short_description = _('Rule name')

    def generateExpenses(self, request=None, datetimeTuple=None):
        from danceschool.financial.helpers.expenses import createExpenseItemsForVenueRental
        return createExpenseItemsForVenueRental(
            rule=self, request=request, datetimeTuple=datetimeTuple
        )

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
    room = models.OneToOneField(
        Room, related_name='rentalinfo', verbose_name=_('Room'),
        on_delete=models.CASCADE
    )

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return _('%s at %s' % (self.room.name, self.room.location.name))
    ruleName.fget.short_description = _('Rule name')

    def generateExpenses(self, request=None, datetimeTuple=None):
        from danceschool.financial.helpers.expenses import createExpenseItemsForVenueRental
        return createExpenseItemsForVenueRental(
            rule=self, request=request, datetimeTuple=datetimeTuple
        )

    def __str__(self):
        return str(_('Rental expense information for: %s at %s' % (
            self.room.name, self.room.location.name
        )))

    class Meta:
        verbose_name = _('Room rental information')
        verbose_name_plural = _('Rooms\' rental information')


class StaffDefaultWage(RepeatedExpenseRule):
    '''
    This model is used to store default wage information on rental periods and rates
    for individual rooms.  If a rental rate does not exist for a room,
    or if it is specified that the room rental rate not be applied,
    then the location's rental rate and parameters are used instead.
    '''
    category = models.OneToOneField(
        EventStaffCategory,
        verbose_name=_('Category'),
        help_text=_(
            'If left blank, then this expense rule will be used for all ' +
            'categories.  If a category-specific rate is specified, then that ' +
            'will be used instead.  If nothing is specified for a staff member, ' +
            'then the default hourly rate for each category will be used.'
        ),
        on_delete=models.CASCADE,
        related_name='defaultwage'
    )

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return self.category.name
    ruleName.fget.short_description = _('Rule name')

    def generateExpenses(self, request=None, datetimeTuple=None):
        from danceschool.financial.helpers.expenses import createExpenseItemsForEvents
        return createExpenseItemsForEvents(rule=self, request=request, datetimeTuple=datetimeTuple)

    def __str__(self):
        return str(_('Default wage information: {category}'.format(category=self.ruleName)))

    class Meta:
        ordering = ('category__name',)
        verbose_name = _('Default staff wage')
        verbose_name_plural = _('Default staff wages')


class StaffMemberWageInfo(RepeatedExpenseRule):
    '''
    This model is used to store information on wages
    for individual staff members staffed in particular ways.
    '''
    staffMember = models.ForeignKey(
        StaffMember, related_name='expenserules', verbose_name=_('Staff member'),
        on_delete=models.CASCADE,
    )

    category = models.ForeignKey(
        EventStaffCategory,
        verbose_name=_('Category'),
        null=True, blank=True,
        help_text=_(
            'If left blank, then this expense rule will be used for all ' +
            'categories.  If a category-specific rate is specified, then that ' +
            'will be used instead.  If nothing is specified for a staff member, ' +
            'then the default hourly rate for each category will be used.'
        ),
        on_delete=models.SET_NULL,
    )

    @property
    def ruleName(self):
        ''' overrides from parent class '''
        return _('%s: %s' % (self.staffMember.fullName, self.category or 'All unspecified categories'))
    ruleName.fget.short_description = _('Rule name')

    def generateExpenses(self, request=None, datetimeTuple=None):
        from danceschool.financial.helpers.expenses import createExpenseItemsForEvents
        return createExpenseItemsForEvents(
            rule=self, request=request, datetimeTuple=datetimeTuple
        )

    def __str__(self):
        return str(_('%s wage/salary information for: %s' % (
            self.category or 'Rental', self.staffMember.fullName
        )))

    class Meta:
        unique_together = ('staffMember', 'category')
        ordering = ('staffMember', 'category__name')
        verbose_name = _('Staff member salary information')
        verbose_name_plural = _('Staff members\' wage/salary information')


class GenericRepeatedExpense(RepeatedExpenseRule):
    '''
    This model is used to store repeated expenses that are not specifically tied to location
    rental or event staffing.  That is, expenses are generated under these rules regardless
    of whether any series or events are booked.
    '''

    name = models.CharField(_('Give this expense generation rule a name'), max_length=100, unique=True)

    # String reference to avoid circular import with expenses.py
    category = models.ForeignKey(
        'financial.ExpenseCategory', verbose_name=_('Category'), null=True, on_delete=models.SET_NULL,
    )

    # An expense rule is associated with a transaction party, which can be a User, a StaffMember,
    # a Location, or just a name of the party.
    payTo = models.ForeignKey(
        TransactionParty, null=True, verbose_name=_('Pay to'), on_delete=models.SET_NULL,
    )

    markApproved = models.BooleanField(_('Automatically mark this expense as approved'), default=False)
    markPaid = models.BooleanField(_('Automatically mark this expense as paid'), default=False)
    paymentMethod = models.CharField(
        _('Payment method'),
        max_length=50, null=True, blank=True,
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
        super().clean()

    def generateExpenses(self, request=None, datetimeTuple=None):
        from danceschool.financial.helpers.expenses import createGenericExpenseItems
        return createGenericExpenseItems(rule=self, request=request, datetimeTuple=datetimeTuple)

    def __str__(self):
        return str(_('Repeated expense rule: %s' % self.name))

    class Meta:
        ordering = ('name',)
        verbose_name = _('Other repeated expense')
        verbose_name_plural = _('Other repeated expenses')
