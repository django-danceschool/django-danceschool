from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class GuestListAppConfig(AppConfig):
    name = 'danceschool.guestlist'
    verbose_name = _('Guest Lists')

    def ready(self):
        from danceschool.core.models import Event
        from .models import GuestList

        from django.db.models import Q

        @property
        def guestLists(self):
            filters = (
                Q(individualEvents=self) |
                Q(eventSessions=self.session) |
                Q(eventCategories=self.category) |
                Q(seriesCategories=self.category)
            )

            return GuestList.objects.filter(filters)

        Event.add_to_class('guestLists',guestLists)
