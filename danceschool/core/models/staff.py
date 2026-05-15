from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import F, ExpressionWrapper, DurationField
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from djangocms_text.fields import HTMLField
from filer.fields.image import FilerImageField
from calendar import month_name
import uuid
import logging

from ..mixins import EmailRecipientMixin
from .event_base import Event
from .event_occurrences import EventOccurrence

logger = logging.getLogger(__name__)


class EventStaffCategory(models.Model):
    name = models.CharField(_('Name'), max_length=50, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Event staff category')
        verbose_name_plural = _('Event staff categories')


class StaffMember(models.Model):
    '''
    StaffMembers include instructors and anyone else who you may wish to
    associate with specific events or activities.
    '''

    # These fields are separate from the user fields because sometimes
    # individuals go publicly by a different name than they may privately.
    firstName = models.CharField(_('First name'), max_length=50, null=True, blank=True)
    lastName = models.CharField(_('Last name'), max_length=50, null=True, blank=True)

    # Although Staff members may be defined without user accounts, this precludes
    # them from having access to the school's features, and is not recommended.
    userAccount = models.OneToOneField(
        User, verbose_name=_('User account'), null=True, blank=True,
        on_delete=models.SET_NULL
    )

    # By default, only the public email is listed on public-facing pages, and
    # telephone contact information are not listed on public-facing pages either.
    publicEmail = models.CharField(
        _('Public Email Address'), max_length=100,
        help_text=_(
            'This is the email address used on the site if the instructor is ' +
            'available for private lessons.'
        ),
        blank=True
    )
    privateEmail = models.CharField(
        _('Private Email Address'), max_length=100,
        help_text=_(
            'This is the personal email address of the instructor for the instructor directory.'
        ),
        blank=True
    )
    phone = models.CharField(
        _('Telephone'), max_length=25,
        help_text=_(
            'Instructor phone numbers are for the instructor directory only, ' +
            'and should not be given to students.'
        ),
        blank=True, null=True
    )

    image = FilerImageField(
        verbose_name=_('Staff photo'), on_delete=models.SET_NULL, blank=True,
        null=True, related_name='staff_image'
    )
    bio = HTMLField(
        verbose_name=_('Bio text'),
        help_text=_(
            'Insert the instructor\'s bio here.  Use HTML to include videos, ' +
            'formatting, etc.'
        ),
        null=True, blank=True
    )

    categories = models.ManyToManyField(
        EventStaffCategory, verbose_name=_('Included in staff categories'), blank=True,
        help_text=_(
            'When choosing staff members, the individuals available to staff ' +
            'will be limited based on the categories chosen here. If the ' +
            'individual is an instructor, also be sure to set the instructor ' +
            'information below.'
        )
    )

    # This field is a unique key that is used in the URL for the
    # staff member's personal calendar feed.
    feedKey = models.UUIDField(
        verbose_name=_('Calendar/RSS feed key'), default=uuid.uuid4, editable=False
    )

    @property
    def fullName(self):
        return ' '.join([self.firstName or '', self.lastName or ''])
    fullName.fget.short_description = _('Name')

    @property
    def activeThisMonth(self):
        return self.eventstaffmember_set.filter(
            event__year=timezone.now().year, event__month=timezone.now().month
        ).exists()
    activeThisMonth.fget.short_description = _('Staffed this month')

    @property
    def activeUpcoming(self):
        return self.eventstaffmember_set.filter(event__endTime__gte=timezone.now()).exists()
    activeUpcoming.fget.short_description = _('Staffed for upcoming events')

    def __str__(self):
        return self.fullName

    class Meta:
        ''' Prevents accidentally adding multiple staff members with the same name. '''
        unique_together = ('firstName', 'lastName')
        verbose_name = _('Staff member')
        verbose_name_plural = _('Staff members')
        ordering = ('lastName', 'firstName')

        permissions = (
            ('view_staff_directory', _('Can access the staff directory view')),
            ('view_school_stats', _('Can view statistics about the school\'s performance.')),
            (
                'can_autocomplete_staffmembers',
                _('Able to use customer and staff member autocomplete features (in admin forms)')
            ),
        )


class Instructor(models.Model):
    '''
    These go on the instructors page.
    '''
    class InstructorStatus(models.TextChoices):
        roster = ('R', _('Regular Instructor'))
        assistant = ('A', _('Assistant Instructor'))
        training = ('T', _('Instructor-in-training'))
        guest = ('G', _('Guest Instructor'))
        retiredGuest = ('Z', _('Former Guest Instructor'))
        retired = ('X', _('Former/Retired Instructor'))
        hidden = ('H', _('Publicly Hidden'))

    staffMember = models.OneToOneField(
        StaffMember, verbose_name=_('Staff member'), on_delete=models.CASCADE,
        primary_key=True
    )

    status = models.CharField(
        _('Instructor status'), max_length=1, choices=InstructorStatus.choices,
        default=InstructorStatus.hidden,
        help_text=_(
            'Instructor status affects the visibility of the instructor on ' +
            'the site, but is separate from the "categories" of event ' +
            'staffing on which compensation is based.'
        )
    )
    availableForPrivates = models.BooleanField(
        _('Available for private lessons'), default=True,
        help_text=_(
            'Check this box if you would like to be listed as available ' +
            'for private lessons from students.'
        )
    )

    @property
    def assistant(self):
        return self.status == self.InstructorStatus.assistant
    assistant.fget.short_description = _('Is assistant')

    @property
    def guest(self):
        return self.status == self.InstructorStatus.guest
    guest.fget.short_description = _('Is guest')

    @property
    def retired(self):
        return self.status == self.InstructorStatus.retired
    retired.fget.short_description = _('Is retired')

    @property
    def hide(self):
        return self.status == self.InstructorStatus.hidden
    retired.fget.short_description = _('Is hidden')

    @property
    def activeGuest(self):
        return (
            self.status == self.InstructorStatus.guest and
            self.activeUpcoming
        )
    retired.fget.short_description = _('Is upcoming guest')

    @property
    def fullName(self):
        return self.staffMember.fullName

    def __str__(self):
        return self.fullName

    class Meta:
        verbose_name = _('Instructor')
        verbose_name_plural = _('Instructors')
        permissions = (
            ('update_instructor_bio', _('Can update instructors\' bio information')),
            ('view_own_instructor_stats', _('Can view one\'s own statistics (if an instructor)')),
            ('view_other_instructor_stats', _('Can view other instructors\' statistics')),
            (
                'view_own_instructor_finances',
                _('Can view one\'s own financial/payment data (if a staff member)')
            ),
            (
                'view_other_instructor_finances',
                _('Can view other staff members\' financial/payment data')
            ),
        )


class EventStaffMember(EmailRecipientMixin, models.Model):
    '''
    Events have staff members of various types.  Instructors and
    substitute teachers are defaults, and substitution has its own proxy
    model as well.  However, other types may be created by
    overriding StaffType.
    '''
    category = models.ForeignKey(
        EventStaffCategory, verbose_name=_('Category'), null=True,
        on_delete=models.SET_NULL
    )

    event = models.ForeignKey(Event, verbose_name=_('Event'), on_delete=models.CASCADE)
    occurrences = models.ManyToManyField(
        EventOccurrence, blank=True, verbose_name=_('Applicable event occurrences')
    )

    staffMember = models.ForeignKey(
        StaffMember, verbose_name=_('Staff Member'), on_delete=models.CASCADE
    )
    replacedStaffMember = models.ForeignKey(
        'self', verbose_name=_('Replacement for'), related_name='replacementFor',
        null=True, blank=True, on_delete=models.SET_NULL
    )

    specifiedHours = models.FloatField(
        _('Number of hours (optional)'),
        help_text=_(
            'If unspecified, then the net number of hours is based on the ' +
            'duration of the applicable event occurrences.'
        ),
        null=True, blank=True, validators=[MinValueValidator(0)]
    )

    data = models.JSONField(_('Additional data'), default=dict, blank=True)

    # For keeping track of who submitted and when.
    submissionUser = models.ForeignKey(
        User, verbose_name=_('Submission User'), null=True,
        on_delete=models.SET_NULL
    )
    creationDate = models.DateTimeField(_('Creation date'), auto_now_add=True)
    modifyDate = models.DateTimeField(_('Last modified date'), auto_now=True)

    @property
    def allocationByOccurrence(self):
        '''
        Return a fraction of the event time associated with each occurrence so
        that things like event staff expenses can be allocated across event
        occurrences.
        '''
        occurrences = (
            self.occurrences.filter(cancelled=False).annotate(
                dur=ExpressionWrapper(
                    F('endTime') - F('startTime'), output_field=DurationField()
                ),
            ) or
            self.event.eventoccurrence_set.filter(cancelled=False).annotate(
                dur=ExpressionWrapper(
                    F('endTime') - F('startTime'), output_field=DurationField()
                ),
            )
        )
        sum_dur = sum([x.dur.total_seconds() for x in occurrences])
        total_dur = (self.specifiedHours or 0)*3600 or sum_dur

        return {
            (x.id, x.event.id): {
                'allocation': x.dur.total_seconds()/sum_dur,
                'total_duration': total_dur,
                'duration': (
                    (x.dur.total_seconds()/sum_dur) * total_dur
                )
            }
            for x in occurrences
        }

    @property
    def netHours(self):
        '''
        For regular event staff, this is the net hours worked for financial purposes.
        For Instructors, netHours is calculated net of any substitutes.
        '''
        if self.specifiedHours is not None:
            return self.specifiedHours

        occurrences = self.occurrences.filter(cancelled=False)
        if occurrences:
            return sum([x.duration for x in self.occurrences.filter(cancelled=False)])

        return self.event.duration
    netHours.fget.short_description = _('Net hours')

    def get_default_recipients(self):
        ''' Overrides EmailRecipientMixin '''
        this_email = getattr(self.staffMember, 'privateEmail', None)
        return [this_email, ] if this_email else []

    def get_email_context(self, **kwargs):
        ''' Overrides EmailRecipientMixin '''

        includeName = kwargs.pop('includeName', True)
        includeEvent = kwargs.pop('includeEvent', True)
        context = super().get_email_context(**kwargs)

        if includeName:
            context.update({
                'first_name': self.staffMember.firstName,
                'last_name': self.staffMember.lastName,
            })

        if includeEvent:
            context['event'] = self.event.get_email_context()

        return context

    def __init__(self, *args, **kwargs):
        '''
        Cache some initial properties to make it easier for signal handlers in
        other apps to detect changes.
        '''
        super().__init__(*args, **kwargs)
        if self.pk:
            for prop in [
                'category', 'staffMember', 'replacedStaffMember', 'specifiedHours'
            ]:
                setattr(self, f'__original_{prop}', self.__dict__.get(prop, None))

    def __str__(self):
        replacements = {
            'type': _('Event Staff'),
            'name': getattr(getattr(self, 'staffMember', None), 'fullName', _('Unknown')),
            'as': _('as'),
            'category': getattr(getattr(self, 'category', None), 'name', _('Unknown')),
            'for': _('for'),
            'eventName': getattr(getattr(self, 'event', None), 'name', _('Unknown')),
        }
        return '%(type)s: %(name)s %(as)s %(category)s %(for)s %(eventName)s' % replacements

    class Meta:
        ordering = ('event', 'staffMember__lastName', 'staffMember__firstName')
        unique_together = ('staffMember', 'event', 'category', 'replacedStaffMember')
        verbose_name = _('Event staff member')
        verbose_name_plural = _('Event staff members')


class SubstituteTeacher(EventStaffMember):
    '''
    This proxy model is used when keeping track of substitute teaching/staffing.
    The model may be used for all types of staff, but we use the proxy model
    for substitute reporting because this allows the possibility of adding
    additional validation on substitutes only.
    '''

    def __str__(self):
        replacements = {
            'name': self.staffMember.fullName,
            'subbed': _(' subbed: '),
            'month': _(month_name[self.event.month or 0]),
            'year': self.event.year,
        }
        if not self.replacedStaffMember:
            return '%(name)s %(subbed)s: %(month)s %(year)s' % replacements

        replacements.update({
            'subbed': _(' subbed for '),
            'staffMember': self.replacedStaffMember.staffMember.fullName
        })
        return '%(name)s %(subbed)s %(staffMember)s: %(month)s %(year)s' % replacements

    def clean(self):
        ''' Ensures no SubstituteTeacher without indicating who they replaced. '''
        if not self.replacedStaffMember:
            raise ValidationError(_('Must indicate which staff member was replaced.'))

    class Meta:
        proxy = True
        permissions = (
            ('report_substitute_teaching', _('Can access the substitute reporting form')),
        )
        verbose_name = _('Substitute staff member')
        verbose_name_plural = _('Substitute staff members')
