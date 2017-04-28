'''
This file defines a variety of preferences that must be set in the DB,
but can be changed dynamically.
'''

from django.utils.translation import ugettext_lazy as _

from dynamic_preferences.types import BooleanPreference, StringPreference, Section
from dynamic_preferences.registries import global_preferences_registry

# we create some section objects to link related preferences together

requirements = Section('requirements', _('Class Requirements'))


################################
# Class Requirements Preferences
#
@global_preferences_registry.register
class EnableRequirements(BooleanPreference):
    section = requirements
    name = 'enableRequirements'
    verbose_name = _('Requirements Enabled')
    help_text = _('If this box is unchecked, then all requirement checks during registration will be disabled.')
    default = True


@global_preferences_registry.register
class RequirementErrorMessage(StringPreference):
    section = requirements
    name = 'errorMessage'
    verbose_name = _('Error message for unmet requirements')
    help_text = _('This message will be appended to any error message with a list of requirements not met.  Individual requirements may be set to produce either errors or warnings.')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs


@global_preferences_registry.register
class RequirementWarningMessage(StringPreference):
    section = requirements
    name = 'warningMessage'
    verbose_name = _('Warning message for unmet requirements')
    help_text = _('This message will be appended to any warning message with a list of requirements not met.  Individual requirements may be set to produce either errors or warnings.')
    default = ''

    def get_field_kwargs(self):
        field_kwargs = super(self.__class__,self).get_field_kwargs()
        field_kwargs['required'] = False
        return field_kwargs
