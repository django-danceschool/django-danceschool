from django.utils.translation import gettext_lazy as _

from .registries import model_templates_registry, ModelTemplateBase
from .models import Series, PublicEvent


@model_templates_registry.register
class BaseEventTemplate(ModelTemplateBase):
    model = PublicEvent
    template_name = 'core/event_pages/individual_event.html'
    description = _('Default event template')


@model_templates_registry.register
class BaseSeriesTemplate(ModelTemplateBase):
    model = Series
    template_name = 'core/event_pages/individual_class.html'
    description = _('Default class series template')


@model_templates_registry.register
class DirectRegisterEventTemplate(ModelTemplateBase):
    model = PublicEvent
    template_name = 'core/event_pages/individual_event_direct.html'
    description = _('With direct checkout button')


@model_templates_registry.register
class DirectRegisterSeriesTemplate(ModelTemplateBase):
    model = Series
    template_name = 'core/event_pages/individual_class_direct.html'
    description = _('With direct checkout button')
