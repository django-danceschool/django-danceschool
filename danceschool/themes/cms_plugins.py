from django.utils.translation import ugettext_lazy as _

from djangocms_picture.cms_plugins import PicturePlugin
from cms.plugin_pool import plugin_pool

from danceschool.core.mixins import PluginTemplateMixin
from danceschool.core.registries import plugin_templates_registry, PluginTemplateBase

class PictureSplashTemplatePlugin(PicturePlugin):
    '''
    A subclass of the Django CMS PicturePlugin that can be used just to select
    a photo for inclusion as the splash page in a theme.  Your theme will need
    to override 'djangocms_picture/splash_image/picture.html' to place the
    splash image appropriately in the template (e.g. using the <header> tag).
    '''

    name = _('Template Splash Image')

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
        return 'djangocms_picture/splash_image/picture.html'

plugin_pool.register_plugin(PictureSplashTemplatePlugin)
