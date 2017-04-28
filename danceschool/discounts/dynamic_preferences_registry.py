from dynamic_preferences.types import BooleanPreference, Section
from dynamic_preferences.registries import global_preferences_registry


general = Section('general', 'General Settings')


@global_preferences_registry.register
class EnableDiscounts(BooleanPreference):
    section = general
    name = 'discountsEnabled'
    verbose_name = 'Discounts and Add-ons enabled'
    help_text = 'Uncheck this to disable the application of all discounts'
    default = True
