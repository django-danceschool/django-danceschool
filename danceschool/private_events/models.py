from django.db import models
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from colorful.fields import RGBColorField

from danceschool.core.models import Event, EventCategory, EventOccurrence


class PrivateEventCategory(EventCategory):
    '''
    Private events have their own categorization relative to public events,
    though the schema is the same because they both inherit from EventCategory.
    '''
    requiredGroup = models.ForeignKey(Group,verbose_name=_('Group required to add events to this category.'),null=True,blank=True)
    displayColor = RGBColorField(_('Calendar display color'),default='#0000FF')

    class Meta:
        verbose_name = _('Private events category')
        verbose_name_plural = _('Private events categories')


class PrivateEvent(Event):
    '''
    Calendar events may have multiple occurrences.
    '''

    title = models.CharField(_('Title'),max_length=100,help_text=_('Give the event a title'))
    category = models.ForeignKey(PrivateEventCategory,null=True,blank=True,verbose_name=_('Category'))

    @property
    def name(self):
        '''
        Overrides property from Event base class.
        '''
        return self.title

    descriptionField = models.TextField(_('Description'),null=True,blank=True)

    @property
    def description(self):
        '''
        Overrides property from Event base class.
        '''
        return self.descriptionField
    description.fget.short_description = _('Description')

    # Private events can have a location entered other than an officially-listed location
    locationString = models.CharField(_('Other location'),max_length=200,null=True,blank=True,help_text=_('If this event is not at a public event location, then enter it here.'))
    link = models.URLField(_('Optional link'),blank=True,help_text=_('Optionally include the URL to anything that may be relevant for this event.'))

    displayToGroup = models.ForeignKey(Group, null=True, blank=True,verbose_name=_('Display to group'),help_text=_('If this is set, then only these users will see this event on their calendar.'))
    displayToUsers = models.ManyToManyField(User,verbose_name=_('Display to users'),limit_choices_to={'is_staff': True},blank=True,help_text=_('If this is set, then only chosen users will see this event on their calendar.'))

    def __str__(self):
        try:
            return '%s: %s' % (self.name, getattr(self.eventoccurrence_set.first(),'startTime').strftime('%a., %B %d, %Y, %I:%M %p'))
        except AttributeError:
            # Event has no occurrences
            return self.name

    def save(self, *args, **kwargs):
        ''' Set registration status to hidden if it is not specified otherwise '''
        if not self.status:
            self.status == Event.RegStatus.hidden
        super(PrivateEvent,self).save(*args,**kwargs)

    class Meta:
        verbose_name = _('Private event/calendar item')
        verbose_name_plural = _('Private events/calendar items')


class EventReminder(models.Model):
    event = models.ForeignKey(Event,verbose_name=_('Event'))
    eventOccurrence = models.ForeignKey(EventOccurrence,verbose_name=_('Event Occurrence'))

    time = models.DateTimeField(_('Date/Time'))

    notifyList = models.ManyToManyField(User, limit_choices_to={'is_staff': True}, verbose_name=_('Notification List'))
    completed = models.BooleanField(_('Completed'),default=False,help_text=_('This will be set to true once the reminder has been sent.'))

    def save(self,*args,**kwargs):
        if hasattr(self,'event') and not hasattr(self,'eventOccurrence'):
            self.eventOccurrence = self.event.eventoccurrence_set.first()
        if hasattr(self,'eventOccurrence') and not hasattr(self,'event'):
            self.event = self.eventOccurrence.event
        if self.eventOccurrence.event != self.event:
            raise ValidationError(_('Event and EventOccurrence must match!'))
        super(EventReminder,self).save(*args,**kwargs)

    def __str__(self):
        return _('Reminder for ' + self.eventOccurrence.event.name + ': ' + self.time.strftime('%a., %B %d, %Y, %I:%M %p') or '')

    class Meta:
        ordering = ('time',)
        verbose_name = _('Event reminder')
        verbose_name_plural = _('Event reminders')
