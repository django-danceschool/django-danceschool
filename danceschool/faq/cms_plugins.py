from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin

from django.utils.translation import ugettext_lazy as _

from .models import FAQSinglePluginModel, FAQCategoryPluginModel, FAQ


class FAQTOCPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('FAQ Table of Contents (auto-generated from FAQs on page)')
    render_template = 'faq/FAQ_TOC.html'
    cache = True
    module = _('FAQs')


class FAQAllPlugin(CMSPluginBase):
    model = CMSPlugin
    name = _('List of All FAQs')
    render_template = 'faq/FAQs.html'
    cache = True
    module = _('FAQs')

    def render(self, context, instance, placeholder):
        listing = FAQ.objects.filter(draft=False)

        context.update({
            'faq_list': listing,
        })
        return context


class FAQCategoryPlugin(CMSPluginBase):
    model = FAQCategoryPluginModel
    name = _('List of FAQs by Category')
    render_template = 'faq/FAQs.html'
    cache = True
    module = _('FAQs')

    def render(self, context, instance, placeholder):
        listing = FAQ.objects.filter(category=instance.category,draft=False)

        context.update({
            'faq_list': listing,
        })
        return context


class SingleQuestionPlugin(CMSPluginBase):
    model = FAQSinglePluginModel
    name = _('Individual FAQ Item')
    render_template = 'faq/single_FAQ.html'
    cache = True
    module = _('FAQs')

    def render(self, context, instance, placeholder):
        context.update({
            'faq_list': [instance.question,],
        })
        return context


plugin_pool.register_plugin(FAQTOCPlugin)
plugin_pool.register_plugin(FAQAllPlugin)
plugin_pool.register_plugin(FAQCategoryPlugin)
plugin_pool.register_plugin(SingleQuestionPlugin)
