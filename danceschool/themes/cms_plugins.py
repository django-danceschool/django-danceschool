from django.utils.translation import ugettext_lazy as _

from djangocms_picture.cms_plugins import PicturePlugin
from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin

from danceschool.core.mixins import PluginTemplateMixin
from danceschool.core.registries import plugin_templates_registry, PluginTemplateBase

from .models import SimpleBootstrapCardModel, BootstrapRowModel, BootstrapColumnModel, BootstrapCarousel, BootstrapCarouselSlide
from .constants import CAROUSEL_DEFAULT_SIZE, DEVICE_SIZES
from .helpers import concat_classes
from .forms import BootstrapRowForm


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
    model = BootstrapRowModel
    name = _('Grid Row')
    form = BootstrapRowForm
    render_template = 'bootstrap/row_default.html'
    cache = True
    module = _('Bootstrap')
    allow_children = True
    child_classes = ['BootstrapColumnPlugin',]

    # change_form_template = 'djangocms_bootstrap4/admin/grid_row.html'
    # render_template = 'djangocms_bootstrap4/grid_row.html'

    fieldsets = [
        (None, {
            'fields': (
                'create',
                'template',
            )
        }),
    ]

    def save_model(self, request, obj, form, change):
        super(BootstrapRowPlugin, self).save_model(request, obj, form, change)
        data = form.cleaned_data
        for x in range(int(data['create']) if data['create'] is not None else 0):
            extra = {}
            for size in DEVICE_SIZES:
                extra['{}_col'.format(size)] = data.get(
                    'create_{}_col'.format(size)
                )
            col = BootstrapColumnModel(
                parent=obj,
                placeholder=obj.placeholder,
                language=obj.language,
                position=obj.numchild,
                plugin_type=BootstrapColumnPlugin.__name__,
                **extra
            )
            obj.add_child(instance=col)

    def render(self, context, instance, placeholder):
        # instance.attributes['class'] = 'row'

        return super(BootstrapRowPlugin, self).render(
            context, instance, placeholder
        )


class BootstrapColumnPlugin(PluginTemplateMixin, CMSPluginBase):
    model = BootstrapColumnModel
    name = _('Grid Column')
    render_template = 'bootstrap/column_default.html'
    module = _('Bootstrap')
    cache = True
    require_parent = True
    parent_classes = ['BootstrapRowPlugin']
    allow_children = True

    # change_form_template = 'djangocms_bootstrap4/admin/grid_column.html'
    # render_template = 'djangocms_bootstrap4/grid_column.html'

    fieldsets = [
        (None, {
            'fields': (
                'template',
                'column_type',
                'column_size',
            )
        }),
        (_('Responsive settings'), {
            'classes': ('collapse',),
            'fields': (
                ['{}_col'.format(size) for size in DEVICE_SIZES],
                ['{}_order'.format(size) for size in DEVICE_SIZES],
                ['{}_ml'.format(size) for size in DEVICE_SIZES],
                ['{}_mr'.format(size) for size in DEVICE_SIZES],
            )
        }),
    ]

    def render(self, context, instance, placeholder):
        column = ''
        classes = instance.get_grid_values()

        if instance.column_size:
            column = 'col-{}'.format(instance.column_size)
        if classes:
            column += ' {}'.format(' '.join(cls for cls in classes if cls))

        # attr_classes = concat_classes([
        #     instance.column_type,
        #     column,
        #     instance.column_alignment,
        #     instance.attributes.get('class'),
        # ])
        # instance.attributes['class'] = attr_classes

        return super(BootstrapColumnPlugin, self).render(
            context, instance, placeholder
        )


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
plugin_pool.register_plugin(BootstrapRowPlugin)
plugin_pool.register_plugin(BootstrapColumnPlugin)
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
