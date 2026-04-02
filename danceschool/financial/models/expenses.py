from datetime import timedelta, datetime

from django.db import models
from django.db.models import Q, F, ExpressionWrapper, DurationField
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from filer.fields.file import FilerFileField
from filer.models import Folder

from danceschool.core.models import Event, EventOccurrence, EventStaffMember
from danceschool.core.constants import getConstant
from danceschool.core.utils.timezone import ensure_localtime
from danceschool.core.utils.sys import isPreliminaryRun

from ..managers import ExpenseItemManager
from .parties import TransactionParty
from .rules import RepeatedExpenseRule


def get_eventStaffMember_ct():
    if isPreliminaryRun():
        return None
    return cache.get_or_set(
        "EVENTSTAFFMEMBER_CT",
        ContentType.objects.get_for_model(EventStaffMember).id, None
    )


class ExpenseCategory(models.Model):
    '''
    These are the different available categories of payment
    '''

    name = models.CharField(
        _('Name'), max_length=50, unique=True,
        help_text=_('Different types of tasks and payments should have different category names')
    )
    defaultRate = models.FloatField(
        _('Default rate'),
        help_text=_(
            'This is the default hourly payment rate for this type of task.  ' +
            'For staff expenses and venue rentals, this will be overridden by ' +
            'the rate specified as default for the venue or staff type.'
        ), null=True, blank=True, validators=[MinValueValidator(0)]
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Expense category')
        verbose_name_plural = _('Expense categories')


class ExpenseItem(models.Model):
    '''
    Expenses may be associated with EventStaff or with Events, or they may be associated with nothing
    '''

    objects = ExpenseItemManager()

    submissionUser = models.ForeignKey(
        User,
        verbose_name=_('Submission user'),
        related_name='expensessubmittedby',
        null=True, blank=True, on_delete=models.SET_NULL,)
    submissionDate = models.DateTimeField(_('Submission date'), auto_now_add=True)

    category = models.ForeignKey(
        ExpenseCategory, verbose_name=_('Category'), null=True, on_delete=models.SET_NULL,
    )

    description = models.CharField(_('Description'), max_length=200, null=True, blank=True)

    hours = models.FloatField(
        _('Hours'),
        help_text=_('Please indicate the number of hours to be paid for.'),
        null=True, blank=True, validators=[MinValueValidator(0)])
    wageRate = models.FloatField(
        _('Wage rate'),
        help_text=_('This should be filled automatically, but can be changed as needed.'),
        null=True, blank=True, validators=[MinValueValidator(0)])
    total = models.FloatField(
        _('Total amount'), blank=True, validators=[MinValueValidator(0)],
        default=0
    )
    adjustments = models.FloatField(
        _('Adjustments/refunds'),
        help_text=_(
            'Record any ex-post adjustments to the amount (e.g. refunds) in this ' +
            'field. A positive amount increases the netExpense, a negative amount ' +
            'reduces the netExpense.'
        ),
        default=0)
    fees = models.FloatField(
        _('Fees'),
        help_text=_(
            'The sum of any transaction fees (e.g. Paypal fees) that were paid ' +
            '<strong>by us</strong>, and should therefore be added to net expense.'
        ),
        default=0)

    paymentMethod = models.CharField(_('Payment method'), max_length=50, null=True, blank=True)

    comments = models.TextField(_('Comments/Notes'), null=True, blank=True)
    attachment = FilerFileField(
        verbose_name=_('Attach File (optional)'), null=True, blank=True,
        related_name='expense_attachment', on_delete=models.SET_NULL
    )

    # An expense item will automatically be associated with an event if it is an
    # automatically-generated _hourly_ expense for venue rental or for event staff.
    # This facilitates event-level financial statements. Non-hourly generated
    # expense items are not automatically affiliated with events.  It is also possible
    # to affiliate an Expense Item with an event via the Expense Reporting Form.
    event = models.ForeignKey(
        Event,
        null=True, blank=True,
        verbose_name=_('Event'),
        help_text=_('If this item is associated with an Event, enter it here.'), on_delete=models.SET_NULL,)

    # For periodic expenses (e.g. hourly/daily/weekly/monthly venue rental,
    # instructor expenses, etc.  This foreign key also replaces the prior
    # relations eventstaffmember and eventvenue, because all automatically
    # generated expenses are now generated against specific repeated expense rules.
    expenseRule = models.ForeignKey(
        RepeatedExpenseRule,
        verbose_name=_('Expense generation rule'),
        null=True, blank=True, on_delete=models.SET_NULL,)

    # For daily/weekly/monthly automatically-generate expenses, this defines the period over which
    # this expense item applies.
    periodStart = models.DateTimeField(_('Expense period start'), null=True, blank=True)
    periodEnd = models.DateTimeField(_('Expense period end'), null=True, blank=True)

    # An expense is associated with a transaction party, which can be a User, a StaffMember,
    # a Location, or just a name of the party.
    payTo = models.ForeignKey(
        TransactionParty, null=True, verbose_name=_('Pay to'), on_delete=models.SET_NULL,
    )

    reimbursement = models.BooleanField(
        _('Reimbursement'),
        help_text=_('Check to indicate that this is a reimbursement expense (i.e. not compensation).'),
        default=False
    )
    approved = models.CharField(
        _('Approved'),
        max_length=100, null=True, blank=True,
        help_text=_(
            'Indicate that expense is approved for payment, or enter any ' +
            'other approval status code information that is needed.'
        ),
    )
    paid = models.BooleanField(
        _('Paid'),
        help_text=_('Check to indicate that payment has been made.'),
        default=False
    )

    approvalDate = models.DateTimeField(_('Approval date'), null=True, blank=True)
    paymentDate = models.DateTimeField(_('Payment date'), null=True, blank=True)

    # This field is used to aggregate expenses over time (e.g. by month).
    # The value of this field is auto-updated using pre-save methods. If
    # there is a class series or an event associated with this expense,
    # then the value is taken from that.  Otherwise, the submission date
    # is used.
    accrualDate = models.DateTimeField(_('Accrual date'))

    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    @property
    def netExpense(self):
        net = getattr(self, 'net', None)
        if net is None:
            net = self.total + self.adjustments + self.fees
        return net
    netExpense.fget.short_description = _('Net expense')

    @property
    def expenseStartDate(self):
        theTime = self.accrualDate
        if self.periodStart:
            theTime = self.periodStart
        elif self.event:
            theTime = self.event.startTime
        return ensure_localtime(theTime)
    expenseStartDate.fget.short_description = _('Start Date')

    @property
    def expenseEndDate(self):
        theTime = self.accrualDate
        if self.periodEnd:
            theTime = self.periodEnd
        elif self.event:
            theTime = self.event.endTime
        return ensure_localtime(theTime)
    expenseEndDate.fget.short_description = _('End Date')

    def getDefaultOccurrenceAllocation(self):
        '''
        Provide a default allocation across event occurrences that is solely
        based on the duration of all occurrences of the event.
        '''
        if not getattr(getattr(self, 'event', None), 'pk', None):
            return {}

        occurrences = self.event.eventoccurrence_set.annotate(
            dur=ExpressionWrapper(
                F('endTime') - F('startTime'), output_field=DurationField()
            ),
        )
        sum_dur = sum([x.dur.total_seconds() for x in occurrences])

        return {
            (x.id, x.event.id): {
                'allocation': x.dur.total_seconds()/sum_dur,
                'total_duration': sum_dur,
                'duration': x.dur.total_seconds(),
            }
            for x in occurrences
        }

    @property
    def allocationByOccurrence(self):
        '''
        Since expenses such as periodic staffing or venue rentals can have
        multiple purposes, they should be allocated among those events and/or
        event occurrences in financial summaries. This method calculates the
        allocation across each occurrence that is associated with the expense.
        '''

        # First, ensure that this expense is allocated across only one content
        # type. Otherwise, the expense is currently inallocable.
        if not self.pk:
            return self.getDefaultOccurrenceAllocation()
        content_types = list(set(self.expensepurpose_set.values_list('content_type', flat=True)))
        if len(content_types) != 1:
            return self.getDefaultOccurrenceAllocation()

        model_class = ContentType.objects.get(id=content_types[0]).model_class()

        # This method also requires that the model have a related_expenses
        # GenericRelation. These are provided by default for EventStaffMember
        # and EventOccurrence, since those expenses can be auto-generated.
        if not hasattr(model_class, 'related_expenses'):
            return self.getDefaultOccurrenceAllocation()

        # Get the associated objects.
        related_objects = model_class.objects.filter(related_expenses__item=self)

        if model_class == EventOccurrence:

            # Uses prefetch cache if eventoccurrence_set was prefetched
            occurrences = list(related_objects.select_related('event'))

            # Compute duration in Python instead of via DB annotation
            for occ in occurrences:
                occ._dur = (occ.endTime - occ.startTime).total_seconds()

            sum_dur = sum(o._dur for o in occurrences)

            return {
                (x.id, x.event_id): {
                    'allocation': x.dur.total_seconds()/sum_dur,
                    'total_duration': sum_dur,
                    'duration': x.dur.total_seconds(),
                }
                for x in occurrences
            }
        elif model_class == EventStaffMember:
            individual_allocations = [
                x.allocationByOccurrence for x in related_objects
            ]
            aggregate_allocation = {}
            total_duration = 0
            for a in individual_allocations:
                for k,v in a.items():
                    aggregate_allocation[k] = {
                        'allocation': (
                            aggregate_allocation.get(k, {}.get('allocation', 0)) +
                            v.get('allocation', 0)*v.get('duration', 0)
                        ),
                        'duration': aggregate_allocation.get(k,{}).get('duration', 0) + v.get('duration', 0),
                    }
                    total_duration += v.get('duration', 0)

            for k,v in aggregate_allocation.items():
                aggregate_allocation[k]['allocation'] /= aggregate_allocation[k]['duration']
                aggregate_allocation[k]['total_duration'] = total_duration
            return aggregate_allocation

    @property
    def allocationByEvent(self):
        '''
        Since expenses such as periodic staffing or venue rentals can have
        multiple purposes, they should be allocated among those events in
        financial summaries. This method calculates the allocation across each
        event that is associated with it, aggregating from the occurrence level.
        '''

        # No need to aggregate occurrence allocations if a specific event is
        # specified.
        if self.event:
            this_dur = (self.event.duration or 0)*3600
            return {
                self.event.id: {
                    'allocation': 1,
                    'duration': this_dur,
                    'total_duration': this_dur,
                }
            }

        occ_allocation = self.allocationByOccurrence
        if not occ_allocation:
            return {}

        event_allocation = {}
        total_duration = 0
        for k,v in occ_allocation.items():
            event_allocation[k[1]] = {
                'allocation': (
                    event_allocation.get(k[1], {}.get('allocation', 0)) +
                    v.get('allocation', 0)*v.get('duration', 0)
                ),
                'duration': event_allocation.get(k[1],{}).get('duration', 0) + v.get('duration', 0)
            }
            total_duration += v.get('duration', 0)

        for k,v in event_allocation.items():
            event_allocation[k]['allocation'] /= event_allocation[k]['duration']
            event_allocation[k]['total_duration'] = total_duration
        return event_allocation

    def getAllocationForEvents(self, events):
        allocation_by_event = self.allocationByEvent
        return sum([
            allocation_by_event.get(e.id, {}).get('allocation', 0)
            for e in events
        ])

    def getAllocationForOccurrences(self, **kwargs):
        occurrences = kwargs.get('occurrences', None)
        if not occurrences:
            return 0
        allocation_by_occurrence = self.allocationByOccurrence
        return sum([
            allocation_by_occurrence.get((o.id, o.event.id), {}).get(
                'allocation', 0
            ) for o in occurrences
        ])

    def getAllocation(self, events=None, occurrences=None):
        if occurrences:
            return self.getAllocationForOccurrences(occurrences=occurrences)
        elif events:
            return self.getAllocationForEvents(events=events)
        else:
            return 1

    def save(self, *args, **kwargs):
        '''
        This custom save method ensures that an expense is not attributed to multiple categories.
        It also ensures that the series and event properties are always associated with any
        type of expense of that series or event.
        '''
        # Set the approval and payment dates if they have just been approved/paid.
        if not hasattr(self, '__paid') or not hasattr(self, '__approved'):
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
        if self.expenseRule and not self.payTo:
            this_loc = getattr(self.expenseRule, 'location', None)
            this_member = getattr(self.expenseRule, 'location', None)

            if this_loc:
                self.payTo = TransactionParty.objects.get_or_create(
                    location=this_loc,
                    defaults={'name': this_loc.name}
                )[0]
            elif this_member:
                self.payTo = TransactionParty.objects.get_or_create(
                    staffMember=this_member,
                    defaults={
                        'name': this_member.fullName,
                        'user': getattr(this_member, 'userAccount', None)
                    }
                )[0]

        # Set the accrual date.  The method for events is based on the end of
        # the event, unless the event was associated with staffing for specific
        # occurrences, in which case the accrual date is the end of those
        # occurrences.

        if not self.accrualDate:
            if self.event:
                last_end = datetime.min.replace(tzinfo=timezone.timezone.utc)

                if self.pk:
                    staff_purpose = self.expensepurpose_set.filter(
                        content_type_id=get_eventStaffMember_ct()
                    )

                    for s in staff_purpose:
                        last_end = max(
                            last_end,
                            getattr(
                                s.purpose.occurrences.order_by('endTime').last(),
                                'endTime', self.event.endTime
                            )
                        )

                if last_end == datetime.min.replace(tzinfo=timezone.timezone.utc):
                    last_end = self.event.endTime
                self.accrualDate = last_end
            elif self.submissionDate:
                self.accrualDate = self.submissionDate
            else:
                self.submissionDate = timezone.now()
                self.accrualDate = self.submissionDate

        # Set the total for hourly work
        if (
            self.hours and not self.wageRate and not self.total and not
            getattr(getattr(self, 'payTo', None), 'location', None) and self.category
        ):
            self.wageRate = self.category.defaultRate
        elif (
            self.hours and not self.wageRate and not self.total and
            getattr(getattr(self, 'payTo', None), 'location', None)
        ):
            self.wageRate = self.payTo.location.rentalRate

        if self.hours and self.wageRate and not self.total:
            self.total = self.hours * self.wageRate

        super().save(*args, **kwargs)
        self.__approved = self.approved
        self.__paid = self.paid
        self.__approvalDate = self.approvalDate
        self.__paymentDate = self.paymentDate

        # If a file is attached, ensure that it is not public, and that it is
        # saved in the 'Expense Receipts' folder
        if self.attachment:
            try:
                self.attachment.folder = Folder.objects.get(name=_('Expense Receipts'))
            except ObjectDoesNotExist:
                pass
            self.attachment.is_public = False
            self.attachment.save()

    def __str__(self):
        if self.accrualDate:
            return '%s %s: %s = %s%s' % (
                getattr(self.category, 'name', str(_('Expense'))),
                self.accrualDate.strftime('%B %Y'),
                self.description, getConstant('general__currencySymbol'),
                self.total
            )
        else:
            return '%s: %s = %s%s' % (
                getattr(self.category, 'name', str(_('Expense'))),
                self.description,
                getConstant('general__currencySymbol'), self.total
            )

    def __init__(self, *args, **kwargs):
        '''
        Permit easy checking to determine if the object
        already exists and has changed on saving
        '''
        super().__init__(*args, **kwargs)
        self.__approved = self.approved
        self.__paid = self.paid
        self.__approvalDate = self.approvalDate
        self.__paymentDate = self.paymentDate

    class Meta:
        ordering = ['-accrualDate', ]
        verbose_name = _('Expense item')
        verbose_name_plural = _('Expense items')

        permissions = (
            ('mark_expenses_paid', _('Mark expenses as paid at the time of submission')),
        )

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'expenseRule','payTo','periodStart','periodEnd','category'
                ],
                name='unique_payment_per_rule_recipient_time_and_category'
            ),
        ]


class ExpensePurpose(models.Model):
    '''
    This model provides a generic relation that makes it possible to correspond
    expense items directly to specific
    '''

    item = models.ForeignKey(
        ExpenseItem,
        verbose_name=_('Expense item purpose'),
        on_delete=models.CASCADE,
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    purpose = GenericForeignKey('content_type', 'object_id')

    # Set when the expense item was generated for a specific occurrence
    # (per-occurrence mode). Null means the item covers the whole event.
    occurrence = models.ForeignKey(
        EventOccurrence,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='expense_purposes',
        verbose_name=_('Event occurrence'),
    )

    def __str__(self):
        return str(_(
            'Purpose for expense item #{item_id}: {purpose}'.format(
                item_id=self.item.id, purpose=self.purpose
            )
        ))
