from django.utils.translation import ugettext_lazy as _

from djangocms_picture.cms_plugins import PicturePlugin
from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin

from danceschool.core.mixins import PluginTemplateMixin
from danceschool.core.registries import plugin_templates_registry, PluginTemplateBase

from .models import SimpleBootstrapCardModel, BootstrapColumnModel, BootstrapCarousel, BootstrapCarouselSlide
from .constants import CAROUSEL_DEFAULT_SIZE


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


class BootstrapCardGroupPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('Card Group')
    render_template = 'bootstrap/card_group.html'
    cache = True
    module = _('Bootstrap')
    allow_children = True
    child_classes = [
        'SimpleBootstrapCardPlugin',
    ]


class BootstrapCardDeckPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('Card Deck')
    render_template = 'bootstrap/card_deck.html'
    cache = True
    module = _('Bootstrap')
    allow_children = True
    child_classes = ['SimpleBootstrapCardPlugin',]


class SimpleBootstrapCardPlugin(PluginTemplateMixin, CMSPluginBase):
    model = SimpleBootstrapCardModel
    name = _('Card')
    cache = True
    module = _('Bootstrap')
    render_template = 'bootstrap/card_default.html'


class BootstrapRowPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('Grid Row')
    render_template = 'bootstrap/row.html'
    cache = True
    module = _('Bootstrap')
    allow_children = True
    child_classes = ['BootstrapColumnPlugin',]


class BootstrapColumnPlugin(PluginTemplateMixin, CMSPluginBase):
    model = BootstrapColumnModel
    name = _('Grid Column')
    render_template = 'bootstrap/column_default.html'
    module = _('Bootstrap')
    cache = True
    require_parent = True
    parent_classes = ['BootstrapRowPlugin']
    allow_children = True


class BootstrapCarouselPlugin(PluginTemplateMixin, CMSPluginBase):
    """
    Components > "Carousel" Plugin
    https://getbootstrap.com/docs/4.0/components/carousel/
    """
    model = BootstrapCarousel
    name = _('Carousel')
    module = _('Bootstrap')
    allow_children = True
    render_template = 'boostrap/carousel_default.html'
    child_classes = ['BootstrapCarouselSlidePlugin']

    fieldsets = [
        (None, {
            'fields': (
                'template',
                ('carousel_aspect_ratio', 'carousel_interval'),
                ('carousel_controls', 'carousel_indicators'),
                ('carousel_keyboard', 'carousel_wrap'),
                ('carousel_ride', 'carousel_pause'),
            )
        }),
    ]

    def render(self, context, instance, placeholder):
        link_classes = ['carousel', 'slide']
        instance.attributes['class'] = link_classes

        return super(BootstrapCarouselPlugin, self).render(
            context, instance, placeholder
        )


class BootstrapCarouselSlidePlugin(CMSPluginBase):
    """
    Components > "Carousel Slide" Plugin
    https://getbootstrap.com/docs/4.0/components/carousel/
    """
    model = BootstrapCarouselSlide
    name = _('Carousel slide')
    module = _('Bootstrap')
    render_template = 'bootstrap/slide_default.html'
    allow_children = True
    parent_classes = ['BootstrapCarouselPlugin']

    fieldsets = [
        (None, {
            'fields': (
                'carousel_image',
                'carousel_content',
            )
        }),
        (_('Link settings'), {
            'classes': ('collapse',),
            'fields': (
                ('external_link', 'internal_link'),
                ('mailto', 'phone'),
                ('anchor', 'target'),
            )
        }),
    ]

    def render(self, context, instance, placeholder):
        parent = instance.parent.get_plugin_instance()[0]
        width = float(context.get('width') or CAROUSEL_DEFAULT_SIZE[0])
        height = float(context.get('height') or CAROUSEL_DEFAULT_SIZE[1])

        if parent.carousel_aspect_ratio:
            aspect_width, aspect_height = tuple(
                [int(i) for i in parent.carousel_aspect_ratio.split('x')]
            )
            height = width * aspect_height / aspect_width

        context['instance'] = instance
        context['link'] = instance.get_link()
        context['options'] = {
            'crop': 10,
            'size': (width, height),
            'upscale': True
        }
        return context


plugin_pool.register_plugin(PictureTemplatePlugin)
plugin_pool.register_plugin(BootstrapCardGroupPlugin)
plugin_pool.register_plugin(BootstrapCardDeckPlugin)
plugin_pool.register_plugin(SimpleBootstrapCardPlugin)
plugin_pool.register_plugin(BootstrapCarouselPlugin)
plugin_pool.register_plugin(BootstrapCarouselSlidePlugin)


@plugin_templates_registry.register
class BootstrapCardDefaultPluginTemplate(PluginTemplateBase):
    plugin = 'SimpleBootstrapCardPlugin'
    template_name = 'bootstrap/card_default.html'
    description = _('Default')


@plugin_templates_registry.register
class BootstrapCarouselDefaultPluginTemplate(PluginTemplateBase):
    plugin = 'BootstrapCarouselPlugin'
    template_name = 'bootstrap/carousel_default.html'
    description = _('Default')
