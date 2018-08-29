from django.utils.translation import ugettext_lazy as _

from djangocms_picture.cms_plugins import PicturePlugin
from cms.plugin_pool import plugin_pool

from danceschool.core.mixins import PluginTemplateMixin
from danceschool.core.registries import plugin_templates_registry, PluginTemplateBase

class PictureTemplatePlugin(PicturePlugin):
    '''
    A subclass of the Django CMS PicturePlugin that can be used just to select
    a photo for inclusion in a theme (the template only inserts the URL).
    '''

    name = _('Template Image')

    fieldsets = [
        (None, {
            'fields': (
                'picture',
                'external_picture',
                'attributes',
            )
        }),
    ]

    def get_render_template(self, context, instance, placeholder):
        ''' Template cannot be chosen when using this plugin. '''
        return 'djangocms_picture/link_only/picture.html'

plugin_pool.register_plugin(PictureTemplatePlugin)
