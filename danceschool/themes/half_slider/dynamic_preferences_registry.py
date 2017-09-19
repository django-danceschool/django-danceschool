'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _
from django.contrib.admin.sites import site

from dynamic_preferences.types import ModelChoicePreference, Section
from dynamic_preferences.registries import global_preferences_registry
from filer.models import Image
from filer.fields.image import AdminImageWidget

from danceschool.core.models import StaffMember


# we create some section objects to link related preferences together

theme = Section('theme', _('Theme Options'))


@global_preferences_registry.register
class FirstSlideImage(ModelChoicePreference):
    section = theme
    name = 'firstSlideImage'
    verbose_name = _('First Slide Image')
    help_text = _('This is the first image shown on the slide carousel of the front page.')
    queryset = Image.objects.all()
    default = None

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['widget'] = AdminImageWidget(rel=StaffMember._meta.get_field('image').rel,admin_site=site)
        return field_kwargs
