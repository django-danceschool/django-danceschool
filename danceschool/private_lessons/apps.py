from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse


class PrivateLessonsConfig(AppConfig):
    name = 'danceschool.private_lessons'
    verbose_name = _('Private Lessons Functions')

    def ready(self):
        from danceschool.core.models import Location
        from . import handlers

        @property
        def jsonPrivateLessonFeed(self):
            '''
            Makes it easy to get location-specific private calendar
            feeds when looping through locations.
            '''
            return reverse('jsonPrivateLessonFeed', args=(self.id,))
        Location.add_to_class('jsonPrivateLessonFeed',jsonPrivateLessonFeed)
