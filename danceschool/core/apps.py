# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig, apps
from django.utils.translation import ugettext_lazy as _
from .registries import plugin_templates_registry


class CoreAppConfig(AppConfig):
    name = 'danceschool.core'
    verbose_name = _('Core School Functions')

    def ready(self):
        # Ensure that signal handlers are loaded
        from . import handlers

        # This will load all cms_plugins.py files under
        # installed apps to identify custom plugin templates
        app_names = [app.name for app in apps.app_configs.values()]
        plugin_templates_registry.autodiscover(app_names)
