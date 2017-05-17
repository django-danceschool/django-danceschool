from django.db import models
from django.utils.translation import ugettext_lazy as _

from calendar import day_name
from multiselectfield import MultiSelectField

from danceschool.core import Instructor, DanceType, Location, DanceRole, Event


class InstructorPrivateLessonDetails(models.Model):
    instructor = models.OneToOneField(Instructor)
    defaultRate = models.FloatField(null=True,blank=True)
    roles = models.ManyToManyField(DanceRole,null=True,blank=True)


class InstructorAvailabilityRule(models.Model):
    instructor = models.ForeignKey(Instructor)

    startDate = models.DateField(_('Start date'))
    endDate = models.DateField(_('End date'))
    weekdays = MultiSelectField(
        verbose_name=_('Limit to days of the week'),
        choices=[(x,day_name[x]) for x in range(0,7)]
    )

    startTime = models.TimeField(_('Start time'))
    endTime = models.TimeField(_('End time'))
    location = models.ForeignKey(Location,verbose_name=_('Location'),null=True,blank=True)


class InstructorAvailability(models.Model):
    instructor = models.ForeignKey(Instructor,verbose_name=_('Instructor'))
    startTime = models.DateTimeField(_('Start time'))
    endTime = models.DateTimeField(_('End time'))
    location = models.ForeignKey(Location,verbose_name=_('Location'),null=True,blank=True)


class PrivateLessonEvent(Event):
    '''
    This is the event object for which an individual registers.  The event is created when the user books a lesson.
    All of the registration logic is still handled by the core app, and this model inherits all of the fields
    associated with other types of events (location, etc.)
    '''

    danceType = models.ForeignKey(DanceType,null=True,blank=True)
    role = models.ForeignKey(DanceRole,null=True,blank=True)

    comments = models.TextField(_('Comments'),help_text=_('Enter any additional comments or important information relating to this private lesson.'),null=True,blank=True)

    # TODO: How to set all the other values for inherited properties based on the fact that this is a private lesson?  Also, the private events app has the same issue.
