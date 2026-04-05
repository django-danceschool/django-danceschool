from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.models import Q
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from polymorphic.models import PolymorphicModel
from polymorphic.managers import PolymorphicManager
import uuid
from datetime import datetime, timedelta
from collections import Counter
from calendar import month_name, day_name
from math import ceil
from itertools import accumulate
import logging

from ..constants import getConstant
from ..mixins import EmailRecipientMixin
from ..utils.timezone import ensure_localtime
from .event_categories import EventSession
from .locations import Location, Room

logger = logging.getLogger(__name__)


def get_closeAfterDays():
    ''' Callable for default used by Event class '''
    return getConstant('registration__closeAfterDays')


class Event(EmailRecipientMixin, PolymorphicModel):
    '''
    All public and private events, including class series, inherit off of this model.
    '''
    class RegStatus(models.TextChoices):
        disabled = ('D', _('Registration disabled'))
        enabled = ('O', _('Registration enabled'))
        heldClosed = ('K', _('Registration held closed (override default behavior)'))
        heldOpen = ('H', _('Registration held open (override default)'))
        linkOnly = ('L', _(
            'Registration open, but hidden from registration page ' +
            '(link required to register)'
        ))
        regHidden = ('C', _(
            'Hidden from registration page, registration closed, potentially visible on calendar.'
        ))
        hidden = ('X', _('Event hidden, registration closed, always hidden from calendar'))

    status = models.CharField(
        _('Registration status'), max_length=1, choices=RegStatus.choices,
        help_text=_('Set the registration status and visibility status of this event.')
    )
    calendarEvent = models.BooleanField(_('Visible on public calendars'), default=True)

    session = models.ForeignKey(
        EventSession, verbose_name=_('Session'),
        help_text=_('Optional event sessions can be used to order events for registration.'),
        null=True, blank=True, on_delete=models.SET_NULL
    )

    # The UUID field is used for private registration links
    uuid = models.UUIDField(_('Unique link ID'), default=uuid.uuid4, editable=False)

    # Although this can be inferred from status, this field is set in the database
    # to allow simpler queryset operations
    registrationOpen = models.BooleanField(_('Registration is open'), default=False)
    registrationOpenDate = models.DateTimeField(
        _('Registration opens at'),
        null=True,
        blank=True,
        help_text=_(
            'If set, registration will automatically open at this date and time. '
            'Only applies when registration status is set to "Registration enabled" '
            'or "Link only". Leave blank to open registration immediately when the '
            'event is saved with one of those statuses.'
        )
    )
    closeAfterDays = models.FloatField(
        _('Registration closes days from first occurrence'),
        default=get_closeAfterDays,
        null=True,
        blank=True,
        help_text=_(
            'Enter positive values to close after first event occurrence, and '
            'negative values to close before first event occurrence.  Leave '
            'blank to keep registration open until the event has ended entirely.'
        )
    )

    created = models.DateTimeField(_('Creation date'), auto_now_add=True)
    modified = models.DateTimeField(_('Last modified date'), auto_now=True)
    submissionUser = models.ForeignKey(
        User, verbose_name=_('Submitted by user'), null=True, blank=True,
        related_name='eventsubmissions', on_delete=models.SET_NULL
    )

    location = models.ForeignKey(
        Location, verbose_name=_('Location'), null=True, blank=True,
        on_delete=models.SET_NULL
    )
    room = models.ForeignKey(
        Room, verbose_name=_('Room'), null=True, blank=True, on_delete=models.SET_NULL
    )

    capacity = models.PositiveIntegerField(_('Event capacity'), null=True, blank=True)

    partnerRequired = models.BooleanField(
        _('Partner required'), default=False,
        help_text=_(
            'If checked, then customers will be prompted to enter the name of ' +
            'their partner when registering.'
        ),
    )

    # These were formerly methods that were given a property decorator, but
    # we need to store them in the DB so that we can have individual class pages
    # without lots of overhead (we would have to pull the whole set of classes
    # every time someone visited a class page) in order to determine which one was
    # /%year%/%month%/%slug%/.  These fields will not be shown in the admin but will
    # be automatically updated on model save.  They can still be called as they were
    # called before.
    month = models.PositiveSmallIntegerField(
        _('Month'), null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    year = models.SmallIntegerField(_('Year'), null=True, blank=True)
    startTime = models.DateTimeField(_('Start time (first occurrence)'), null=True, blank=True)
    endTime = models.DateTimeField(_('End time (last occurrence)'), null=True, blank=True)
    duration = models.FloatField(
        _('Duration in hours'), null=True, blank=True, validators=[MinValueValidator(0)]
    )

    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    # In apps.py, this will be replaced with a custom manager to add annotations
    # for registration being enabled and for past events. It also allows access
    # to QuerySet methods for prefetching occurrences and registrations.
    objects = PolymorphicManager()

    @property
    def localStartTime(self):
        return ensure_localtime(self.startTime)

    @property
    def localEndTime(self):
        return ensure_localtime(self.endTime)

    @property
    def getMonthName(self):
        '''
        This exists as a separate method because sometimes events should really
        belong to more than one month (e.g. class series that persist over multiple months).
        '''
        class_counter = Counter([
            (x.startTime.year, x.startTime.month) for x in self.eventoccurrence_set.all()
        ])
        multiclass_months = [x[0] for x in class_counter.items() if x[1] > 1]
        all_months = [x[0] for x in class_counter.items()]

        if multiclass_months:
            multiclass_months.sort()
            return '/'.join([month_name[x[1]] for x in multiclass_months])

        else:
            return month_name[min(all_months)[1]]
    getMonthName.fget.short_description = _('Month')

    @property
    def name(self):
        '''
        Since other types of events (PublicEvents, class Series, etc.) are subclasses
        of this class, it is a good idea to override this method for those subclasses,
        to provide a more intuitive name.  However, defining this property at the
        event level ensures that <object>.name can always be used to access a readable
        name for describing the event.
        '''
        if self.startTime:
            return _('Event, begins %s' % (ensure_localtime(self.startTime).strftime('%a., %B %d, %Y, %I:%M %p')))
        else:
            return _('Event #%s' % (self.id))
    name.fget.short_description = _('Name')

    @property
    def description(self):
        '''
        Since other types of events (PublicEvents, class Series, etc.) are subclasses
        of this class, it is a good idea to override this method for those subclasses,
        to provide a more intuitive description.  However, defining this property at the
        event level ensures that <object>.description can always be used to access a description
        of the event.
        '''
        return ''
    description.fget.short_description = _('Description')

    @property
    def shortDescription(self):
        '''
        Since other types of events (PublicEvents, class Series, etc.) are subclasses
        of this class, it is a good idea to override this method for those subclasses,
        to provide a more intuitive description.  However, defining this property at the
        event level ensures that <object>.description can always be used to access a short
        description of the event.
        '''
        return ''
    shortDescription.fget.short_description = _('Short description')

    @property
    def organizer(self):
        '''
        Since events can be organized for registration in different ways (e.g. by month,
        by session, or the interaction of the two), this property is used to make it easy
        for templates to include necessary organizing information.  Note that this method
        has nothing to do with the sorting of any queryset in use, which still has to be
        handled elsewhere.
        '''
        rule = getConstant('registration__orgRule')

        # Default grouping is "Other", in case session, month, or weekday are not specified.
        org = {
            'name': _('Other'),
            'nameFirst': {'name': _('Other'), 'sorter': _('Other')},
            'nameSecond': {'name': '', 'sorter': ''},
            'id': None,
        }

        def updateForMonth(self, org):
            ''' Function to avoid repeated code '''
            if self.month:
                org.update({
                    'name': _(month_name[self.month]),
                    'nameFirst': {'name': _(month_name[self.month]), 'sorter': self.month},
                    'id': 'month_%s' % self.month,
                })
            return org

        def updateForSession(self, org):
            ''' Function to avoid repeated code '''
            if self.session:
                org.update({
                    'name': self.session.name,
                    'nameFirst': {'name': _(self.session.name), 'sorter': _(self.session.name)},
                    'id': self.session.pk,
                })
            return org

        if rule in ['SessionFirst', 'SessionAlphaFirst']:
            org = updateForSession(self, org)
            if not org.get('id'):
                org = updateForMonth(self, org)
        elif rule == 'Month':
            org = updateForMonth(self, org)
        elif rule in ['Session', 'SessionAlpha']:
            org = updateForSession(self, org)
        elif rule in ['SessionMonth', 'SessionAlphaMonth']:
            if self.session and self.month:
                org.update({
                    'name': _('%s: %s' % (month_name[self.month], self.session.name)),
                    'nameFirst': {'name': _(month_name[self.month]), 'sorter': self.month},
                    'nameSecond': {'name': _(self.session.name), 'sorter': _(self.session.name)},
                    'id': 'month_%s_session_%s' % (self.month, self.session.pk),
                })
            elif not self.month:
                org = updateForSession(self, org)
            elif not self.session:
                org = updateForMonth(self, org)
        elif rule == 'Weekday':
            w = self.weekday
            d = day_name[w]
            if w is not None:
                org.update({
                    'name': _(d),
                    'nameFirst': {'name': _(d), 'sorter': w},
                    'id': w,
                })
        elif rule == 'MonthWeekday':
            w = self.weekday
            d = day_name[w]
            m = self.month
            mn = month_name[m]
            if w is not None and m:
                org.update({
                    'name': _('%ss in %s' % (d, mn)),
                    'nameFirst': {'name': _(mn), 'sorter': m},
                    'nameSecond': {'name': _('%ss' % d), 'sorter': w},
                    'id': 'month_%s_weekday_%s' % (m, w)
                })
        return org

    @property
    def displayColor(self):
        '''
        This property is overridden for Series, for which the display color is set by
        the dance type and level of the class.
        '''
        if hasattr(self, 'category') and self.category:
            return self.category.displayColor
    displayColor.fget.short_description = _('Display color')

    @property
    def durationMinutes(self):
        ''' Convenience for templates that want to report duration in minutes '''
        return self.duration * 60
    durationMinutes.fget.short_description = _('Duration in minutes')

    def _get_scheduled_close_time(self):
        """
        Calculate when registration should close, returning a datetime or None.
        Returns None if registration should never auto-close (e.g. heldOpen).
        """
        startTime = (
            ensure_localtime(self.startTime) or
            (
                getattr(
                    self.eventoccurrence_set.order_by('startTime').first(),
                    'startTime', None
                ) if self.pk else None
            )
        )
        endTime = (
            ensure_localtime(self.endTime) or
            (
                getattr(
                    self.eventoccurrence_set.order_by('-endTime').first(),
                    'endTime', None
                ) if self.pk else None
            )
        )

        if not startTime or not endTime:
            return None

        if self.closeAfterDays is not None:
            return min(startTime + timedelta(days=self.closeAfterDays), endTime)
        return endTime

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        return [
            x.customer.email for x in self.eventregistration_set.filter(
                cancelled=False,
                customer__isnull=False,
            )
        ]

    def get_email_context(self, **kwargs):
        ''' Overrides EmailRecipientMixin '''
        context = super().get_email_context(**kwargs)
        context.update({
            'id': self.id,
            'name': self.__str__(),
            'title': self.name,
            'start': self.firstOccurrenceTime,
            'next': self.nextOccurrenceTime,
            'last': self.lastOccurrenceTime,
            'url': self.url,
        })
        return context

    def getBasePrice(self, **kwargs):
        '''
        This method is also generally overridden by subclasses of this class, but it is
        defined here to ensure that the method always exists when looping through events.
        '''
        return 0

    # For standard subclasses, basePrice is the non-student, online registration price.
    basePrice = property(fget=getBasePrice)
    basePrice.fget.short_description = _('Base price for online registration')

    def getYearAndMonth(self):

        rule = getConstant('registration__eventMonthRule')

        class_counter = list(Counter([
            (x.startTime.year, x.startTime.month) for x in
            self.eventoccurrence_set.order_by('startTime')
        ]).items())

        # Count occurrences by year and month, and find any months with more than
        # one occurrence in them.  Return the first of these.  If no months
        # have more than one occurrence, return the month of the first occurrence.
        if rule == 'FirstMulti' and class_counter:
            multiclass_months = [x[0] for x in class_counter if x[1] > 1]
            all_months = [x[0] for x in class_counter]

            if multiclass_months:
                return min(multiclass_months)
            elif all_months:
                return min(all_months)
        # Return the month with the most occurrences (ties are broken in favor of earlier months)
        elif rule == 'Most' and class_counter:
            class_counter.sort(key=lambda x: (-x[1], x[0]))
            return class_counter[0][0]
        # Return the month of the last occurrence
        elif rule == 'Last' and class_counter:
            class_counter.sort(key=lambda x: x[0], reverse=True)
            return class_counter[0][0]
        # Return the month of the first occurrence
        elif rule == '1' and class_counter:
            class_counter.sort(key=lambda x: x[0])
            return class_counter[0][0]
        # Return the month of the second occurrence
        elif rule == '2' and class_counter:
            class_counter.sort(key=lambda x: x[0])
            cumulative_list = list(accumulate([x[1] for x in class_counter]))
            if max(cumulative_list) >= 2:
                return class_counter[next(x[0] for x in enumerate(cumulative_list) if x[1] >= 2)][0]
            else:
                return class_counter[len(class_counter) - 1][0]

        return (None, None)

    @property
    def numOccurrences(self):
        return self.eventoccurrence_set.count()
    numOccurrences.fget.short_description = _('# Occurrences')

    @property
    def firstOccurrence(self):
        return self.eventoccurrence_set.order_by('startTime').first()
    firstOccurrence.fget.short_description = _('First occurrence')

    @property
    def firstOccurrenceTime(self):
        if self.firstOccurrence:
            return self.firstOccurrence.localStartTime
        return None
    firstOccurrenceTime.fget.short_description = _('Begins')

    @property
    def nextOccurrence(self):
        return self.eventoccurrence_set.filter(
            startTime__gte=timezone.now()
        ).order_by('startTime').first()
    nextOccurrence.fget.short_description = _('Next occurrence')

    @property
    def nextOccurrenceTime(self):
        if self.nextOccurrence:
            return self.nextOccurrence.localStartTime
        return None
    nextOccurrenceTime.fget.short_description = _('Next occurs')

    @property
    def nextOccurrenceForToday(self):
        dateTime = ensure_localtime(timezone.now()).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return self.getNextOccurrence(dateTime)
    nextOccurrenceForToday.fget.short_description = _(
        'Next occurrence (including today)'
    )

    def getNextOccurrenceForDate(self, date=None):
        if not date:
            dateTime = ensure_localtime(timezone.now()).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif isinstance(date, datetime):
            dateTime = ensure_localtime(date).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            dateTime = ensure_localtime(datetime(date.year, date.month, date.day))
        return self.getNextOccurrence(dateTime)

    def getNextOccurrence(self, dateTime):
        return self.eventoccurrence_set.filter(
            startTime__gte=dateTime
        ).order_by('startTime').first()

    @property
    def lastOccurrence(self):
        return self.eventoccurrence_set.order_by('startTime').last()
    lastOccurrence.fget.short_description = _('Last occurrence')

    @property
    def lastOccurrenceTime(self):
        if self.lastOccurrence:
            return self.lastOccurrence.localEndTime
        return None
    lastOccurrenceTime.fget.short_description = _('Ends')

    @property
    def weekday(self):
        return self.firstOccurrenceTime.weekday()
    weekday.fget.short_description = _('Day of week')

    @property
    def hour(self):
        return self.firstOccurrenceTime.hour
    hour.fget.short_description = _('Hour')

    @property
    def minute(self):
        return self.firstOccurrenceTime.minute
    minute.fget.short_description = _('Minute')

    @property
    def isStarted(self):
        return self.firstOccurrenceTime >= timezone.now()
    isStarted.fget.short_description = _('Has begun')

    @property
    def isCompleted(self):
        return self.lastOccurrenceTime < timezone.now()
    isCompleted.fget.short_description = _('Has ended')

    @property
    def registrationEnabled(self):
        ''' Just checks if this event ever permits/permitted registration '''
        return self.status in [
            self.RegStatus.enabled, self.RegStatus.heldOpen, self.RegStatus.heldClosed
        ]
    registrationEnabled.fget.short_description = _('Registration enabled')

    @property
    def numDropIns(self, includeTemporaryRegs=False):
        filters = Q(cancelled=False) & Q(dropIn=True)
        excludes = Q()

        if includeTemporaryRegs:
            excludes = Q(registration__final=False) & Q(registration__invoice__expirationDate__lte=timezone.now())
        else:
            filters = filters & Q(final=True)
        return self.eventregistration_set.filter(filters).exclude(excludes).count()
    numDropIns.fget.short_description = _('# Drop-ins')

    def getNumRegistered(self, includeTemporaryRegs=False, dateTime=None):
        '''
        Method allows the inclusion of temporary registrations, as well as exclusion of
        temporary registrations that are too new (e.g. for discounts based on the first
        X registrants, we don't want to include people who started tp register later
        than the person in question.
        '''

        filters = Q(cancelled=False) & Q(dropIn=False)
        excludes = Q()

        if includeTemporaryRegs:
            excludes = Q(registration__final=False) & Q(registration__invoice__expirationDate__lte=timezone.now())
            if isinstance(dateTime, datetime):
                excludes = Q(excludes) | (Q(registration__final=False) & Q(registration__dateTime__gte=dateTime))
        else:
            filters = filters & Q(registration__final=True)
        return self.eventregistration_set.filter(filters).exclude(excludes).count()

    @property
    def numRegistered(self):
        return self.getNumRegistered()
    numRegistered.fget.short_description = _('# Registered')

    @property
    def availableRoles(self):
        '''
        Returns the set of roles for this event.  Since roles are not always custom
        specified for event, this looks for the set of available roles in multiple
        places.  If no roles are found, then the method returns an empty list,
        in which case it can be assumed that the event's registration
        is not role-specific.
        '''
        from .event_types import Series
        eventRoles = self.eventrole_set.filter(capacity__gt=0)
        if eventRoles.count() > 0:
            return [x.role for x in eventRoles]
        elif isinstance(self, Series):
            return self.classDescription.danceTypeLevel.danceType.roles.all()
        return []
    availableRoles.fget.short_description = _('Applicable dance roles')

    def numRegisteredForRole(self, role, includeTemporaryRegs=False):
        '''
        Accepts a DanceRole object and returns the number of registrations of that role.
        '''
        filters = Q(cancelled=False) & Q(dropIn=False) & Q(role=role)
        excludes = Q()

        if includeTemporaryRegs:
            excludes = Q(registration__final=False) & Q(registration__invoice__expirationDate__lte=timezone.now())
        else:
            filters = filters & Q(registration__final=True)
        return self.eventregistration_set.filter(filters).exclude(excludes).count()

    @property
    def numRegisteredByRole(self):
        '''
        Return a dictionary listing registrations by all available roles (including no role)
        '''
        role_list = list(self.availableRoles) + [None, ]
        return {getattr(x, 'name', None): self.numRegisteredForRole(x) for x in role_list}
    numRegisteredByRole.fget.short_description = _('# Registered by role')

    def capacityForRole(self, role):
        '''
        Accepts a DanceRole object and determines the capacity for that role at this event.this
        Since roles are not always custom specified for events, this looks for the set of
        available roles in multiple places, and only returns the overall capacity of the event
        if roles are not found elsewhere.
        '''
        from .event_types import Series
        from .event_roles import DanceRole
        if isinstance(role, DanceRole):
            role_id = role.id
        else:
            role_id = role

        eventRoles = self.eventrole_set.filter(capacity__gt=0)
        if eventRoles.count() > 0 and role_id not in [x.role.id for x in eventRoles]:
            ''' Custom role capacities exist but role this is not one of them. '''
            return 0
        elif eventRoles.count() > 0:
            ''' The role is a match to custom roles, so check the capacity. '''
            return eventRoles.get(role=role).capacity

        # No custom roles for this event, so get the danceType roles and use the overall
        # capacity divided by the number of roles
        if isinstance(self, Series):
            try:
                availableRoles = self.classDescription.danceTypeLevel.danceType.roles.all()

                if availableRoles.count() > 0 and role_id not in [x.id for x in availableRoles]:
                    ''' DanceType roles specified and this is not one of them '''
                    return 0
                elif availableRoles.count() > 0 and self.capacity:
                    # Divide the total capacity by the number of roles and round up.
                    return ceil(self.capacity / availableRoles.count())
            except ObjectDoesNotExist as e:
                logger.error('Error in calculating capacity for role: %s' % e)

        # No custom roles and no danceType to get roles from, so return the overall capacity
        return self.capacity

    def soldOutForRole(self, role, includeTemporaryRegs=False):
        '''
        Accepts a DanceRole object and responds if the number of registrations for that
        role exceeds the capacity for that role at this event.
        '''
        base_sold_out = (
            self.numRegisteredForRole(role, includeTemporaryRegs=includeTemporaryRegs) >=
            (self.capacityForRole(role) or 0)
        )
        if base_sold_out:
            return True
        for x in self.eventaddon_set.all():
            if (
                role in x.addOnEvent.availableRoles and
                x.addOnEvent.soldOutForRole(role, includeTemporaryRegs=includeTemporaryRegs)
            ):
                return True
        return False

    @property
    def soldOut(self):
        # Prefer annotation if present (base annotation does not look at
        # addOnEvents).
        if getattr(self, '_sold_out', False) is True:
            return True

        base_sold_out = (self.numRegistered >= (self.capacity or 0))
        if base_sold_out:
            return True
        return (
            True in [x.addOnEvent.soldOut for x in self.eventaddon_set.all()]
        )
    soldOut.fget.short_description = _('Sold Out')

    @property
    def url(self):
        '''
        This property is typically overwritten by each subclass.
        '''
        return None
    url.fget.short_description = _('Event URL')

    def get_absolute_url(self):
        '''
        This is needed for the creation of calendar feeds.
        '''
        return self.url

    @property
    def fieldPrefix(self):
        '''
        This property is usually the name of the model type for events
        (series, public event, etc.), which operates as a prefix for form fields
        in the registration process.
        '''
        return self.polymorphic_ctype.model

    def updateTimes(self, saveMethod=False):
        '''
        Called on model save as well as after an occurrence is saved or deleted.
        Check and update the startTime, endTime, and duration of the event based
        on its occcurrences.
        '''
        changed = False
        occurrences = self.eventoccurrence_set.all() if self.pk else None

        if occurrences:
            new_year, new_month = self.getYearAndMonth()
            new_startTime = occurrences.order_by('startTime').first().startTime
            new_endTime = occurrences.order_by('endTime').last().endTime
            new_duration  = sum([
                x.duration for x in occurrences.filter(cancelled=False)
            ])

            if (
                ((self.year is None) | (self.year != new_year)) |
                ((self.month is None) | (self.month != new_month)) |
                ((self.startTime is None) | (self.startTime != new_startTime)) |
                ((self.endTime is None) | (self.endTime != new_endTime)) |
                ((self.duration is None) | (self.duration != new_duration))
            ):
                self.year = new_year
                self.month = new_month
                self.startTime = new_startTime
                self.endTime = new_endTime
                self.duration = new_duration
                changed = True

        if changed and not saveMethod:
            self.save()

    def scheduleRegistrationTasks(self):
        """
        Revoke any existing scheduled open/close tasks, then schedule new ones
        based on the current state of registrationOpenDate and closeAfterDays.
        Called after every relevant save. Uses .update() on the data field to
        avoid triggering another full save cycle.
        """
        from ..tasks import open_event_registration, close_event_registration
        from huey.contrib.djhuey import HUEY as huey

        if not self.pk:
            return

        data = self.data or {}

        # --- Revoke existing scheduled tasks ---
        for key in ('scheduled_open_task_id', 'scheduled_close_task_id'):
            task_id = data.pop(key, None)
            if task_id:
                try:
                    huey.revoke_by_id(task_id)
                    logger.debug('Revoked task %s (%s)', task_id, key)
                except Exception:
                    # Already executed or not found — safe to ignore
                    logger.debug(
                        'Could not revoke task %s — may have already run', task_id
                    )

        automatic_codes = [self.RegStatus.enabled, self.RegStatus.linkOnly]

        # --- Schedule open task ---
        if self.status in automatic_codes and self.pricingTier:
            open_date = ensure_localtime(self.registrationOpenDate)
            if open_date and open_date > timezone.now():
                result = open_event_registration.schedule(
                    args=(self.pk,), eta=open_date
                )
                data['scheduled_open_task_id'] = result.id
                logger.info(
                    'Scheduled registration open for event %s at %s (task %s)',
                    self.pk, open_date, result.id
                )

        # --- Schedule close task ---
        close_time = self._get_scheduled_close_time()
        if (
            self.status in automatic_codes and
            self.pricingTier and
            close_time and
            close_time > timezone.now()
        ):
            result = close_event_registration.schedule(
                args=(self.pk,), eta=close_time
            )
            data['scheduled_close_task_id'] = result.id
            logger.info(
                'Scheduled registration close for event %s at %s (task %s)',
                self.pk, close_time, result.id
            )

        # Use .update() to persist task IDs without triggering another full save
        Event.objects.filter(pk=self.pk).update(data=data)
        self.data = data

    def updateRegistrationStatus(self, saveMethod=False):
        """
        If called via cron job or otherwise, then update the registrationOpen
        property for this series to reflect any manual override and/or the automatic
        closing of this series for registration. Now includes registrationOpenDate
        awareness in the automatic_codes branch. If a registrationOpenDate is set
        and we haven't reached it yet, treat registration as not yet open.
        """
        logger.debug('Beginning update registration status.  saveMethod=%s' % saveMethod)

        modified = False
        open = self.registrationOpen

        startTime = (
            ensure_localtime(self.startTime) or
            (
                getattr(
                    self.eventoccurrence_set.order_by('startTime').first(),
                    'startTime', None
                )
                if self.pk else None
            )
        )

        # If set to these codes, then registration will be held closed
        force_closed_codes = [
            self.RegStatus.disabled,
            self.RegStatus.heldClosed,
            self.RegStatus.regHidden,
            self.RegStatus.hidden,
        ]
        # If set to these codes, then registration will be held open
        force_open_codes = [
            self.RegStatus.heldOpen
        ]
        # If set to these codes, then registration status will be set at the
        # designated times using scheduled tasks
        automatic_codes = [
            self.RegStatus.enabled,
            self.RegStatus.linkOnly
        ]

        # Determine if registrationOpenDate is blocking us from opening yet
        open_date = ensure_localtime(self.registrationOpenDate)
        open_date_is_future = open_date and timezone.now() < open_date

        if (self.status in force_closed_codes or not self.pricingTier) and open is True:
            open = False
            modified = True
        elif not self.pricingTier:
            open = False
            modified = False
        elif (self.status in force_open_codes and self.pricingTier) and open is False:
            open = True
            modified = True
        elif self.status in automatic_codes:
            close_time = self._get_scheduled_close_time()
            should_be_closed = (
                open_date_is_future or
                (close_time and timezone.now() > close_time)
            )
            should_be_open = (
                not open_date_is_future and
                startTime and
                (not close_time or timezone.now() < close_time)
            )

            if should_be_closed and open is True:
                open = False
                modified = True
            elif should_be_open and open is False:
                open = True
                modified = True

        if modified and not saveMethod:
            logger.debug('Attempting to save event object with registrationOpen: %s' % open)
            self.registrationOpen = open
            self.save(fromUpdateRegistrationStatus=True)
        logger.debug('Returning value: %s' % open)
        return (modified, open)

    def getAllocatedTotals(self, **kwargs):
        '''
        This method handles the allocation of a parent event's base price across
        its add-ons, including the possibility of a residual total.
        '''
        from .event_addons import EventAddOn

        base_price = self.getBasePrice(**kwargs)

        add_ons = self.eventaddon_set.all()
        if (not add_ons) or (kwargs.get('dropIns', 0) > 0):
            return {self.id: base_price}

        explicit_add_ons = add_ons.exclude(
            allocationType=EventAddOn.AllocationType.residual
        ).order_by('order')
        residual_add_ons = add_ons.filter(
            allocationType=EventAddOn.AllocationType.residual
        )

        allocation = {}
        remaining = base_price

        # Always handle explicit allocations first. If the allocation runs out
        # of money to allocate, then subsequent add-ons get no allocation, but
        # are still included in the return value to denote that they are still
        # added on even if no revenue is allocated.
        for a in explicit_add_ons:
            if remaining <= 0:
                this_allocation = 0
            elif a.allocationType == EventAddOn.AllocationType.fixed:
                this_allocation = min(remaining, a.allocationAmount)
            else:
                this_allocation = min(1, a.allocationAmount/100)*remaining

            allocation[a.addOnEvent.id] = this_allocation
            remaining -= this_allocation

        # Now that explicit add-ons have been handled, we can allocate remaining
        # value among the reisdual add-ons in proportion to their base prices.
        # Note the 'or 1' on sum base price to avoid division by zero issues
        # when all remaining events are free.
        base_prices = {
            x.addOnEvent.id: x.addOnEvent.getBasePrice(**kwargs)
            for x in residual_add_ons
        }
        sum_base_price = sum(base_prices.values())
        pre_residual_remaining = remaining

        for k, v in base_prices.items():
            this_allocation = min(v, pre_residual_remaining*(v / (sum_base_price or 1)))
            allocation[k] = this_allocation
            remaining -= this_allocation

        allocation[self.id] = remaining
        return allocation

    def clean(self):
        if (
            self.status in [
                Event.RegStatus.enabled, Event.RegStatus.linkOnly, Event.RegStatus.heldOpen
            ] and not self.capacity
        ):
            raise ValidationError(_('If registration is enabled then a capacity must be set.'))
        if (
            self.status in [
                Event.RegStatus.enabled, Event.RegStatus.linkOnly, Event.RegStatus.heldOpen
            ] and not self.pricingTier
        ):
            raise ValidationError(_('If registration is enabled then a pricing tier must be set.'))
        if self.room and self.location and self.room.location != self.location:
            raise ValidationError(_('Selected room is not part of selected location.'))

    def save(self, *args, **kwargs):
        logger.debug('Save method for Event or subclass called.')
        from_update_status = kwargs.pop('fromUpdateRegistrationStatus', False)

        logger.debug('About to check registration status and update if needed.')
        self.updateTimes(saveMethod=True)

        if self.room and not self.location:
            self.location = self.room.location

        if self.room and self.room.defaultCapacity and not self.capacity:
            self.capacity = self.room.defaultCapacity
        elif self.location and not self.capacity:
            self.capacity = self.location.defaultCapacity

        # Run registration status sync on every save
        _, open_status = self.updateRegistrationStatus(saveMethod=True)
        self.registrationOpen = open_status

        super().save(*args, **kwargs)

        # Update start time and end time for associated event session.
        if self.session:
            self.session.save()

        # After saving, reschedule tasks unless we're being called from
        # updateRegistrationStatus itself (to prevent recursion)
        if not from_update_status:
            self.scheduleRegistrationTasks()

    def __str__(self):
        return str(_('Event: %s' % self.name))

    class Meta:
        verbose_name = _('Series/Event')
        verbose_name_plural = _('All Series/Events')
        ordering = ('-startTime',)
