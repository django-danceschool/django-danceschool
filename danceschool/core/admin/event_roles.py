from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ..models import DanceRole, EventRole


class EventRoleInline(admin.TabularInline):
    model = EventRole
    extra = 1
    classes = ['collapse']

    verbose_name = _('Event-specific dance role')
    verbose_name_plural = _('Event-specific dance roles (override default)')


admin.site.register(DanceRole)
