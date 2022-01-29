# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig, apps
from django.utils.translation import gettext_lazy as _
from .registries import (
    plugin_templates_registry, model_templates_registry,
    extras_templates_registry
)


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
        model_templates_registry.autodiscover(app_names)
        extras_templates_registry.autodiscover(app_names)

        # See django-cms issue #6433. Hopefully this monkeypatch can be removed soon.
        from cms.cms_toolbars import PageToolbar
        from cms.utils import page_permissions

        def monkeypatch_cms_has_publish_permission():
            def has_publish_permission(self):
                has_page = self.page is not None
                publish_permission = False
                if has_page:
                    publish_permission = page_permissions.user_can_publish_page(
                        self.request.user, page=self.page, site=self.current_site)
                if (not has_page or publish_permission) and self.statics:
                    publish_permission = all(
                        sp.has_publish_permission(self.request)
                        for sp in self.dirty_statics)

                return publish_permission

            return has_publish_permission

        PageToolbar.has_publish_permission = monkeypatch_cms_has_publish_permission()
