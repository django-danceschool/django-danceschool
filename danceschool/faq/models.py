from django.db import models
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin

from djangocms_text_ckeditor.fields import HTMLField


class FAQCategory(models.Model):

    name = models.CharField(_('Name'),max_length=200,unique=True)

    # This defines the order number on the FAQ page
    orderNum = models.PositiveIntegerField(_('Order number'),help_text=_('This number specifies the order in which categories will be shown.'), default=0)

    def __str__(self):
        return '%s: %s' % (_('FAQ Category'),self.name)

    class Meta:
        ordering = ('orderNum',)
        verbose_name = _('FAQ category')
        verbose_name_plural = _('FAQ categories')


class FAQ(models.Model):

    category = models.ForeignKey(FAQCategory,null=True,verbose_name=_('Category'))

    question = models.CharField(_('Question'),max_length=200)
    answer = HTMLField(_('Answer'),help_text=_('Answer the question.'))

    # This defines the order number on the FAQ page
    orderNum = models.PositiveIntegerField(_('Order number'),help_text=_('This number specifies the order in which the questions will be shown on the FAQ page.'), default=0)

    draft = models.BooleanField(_('Draft status'),default=False, help_text=_('Check this box to prevent publication.'))

    creationDate = models.DateTimeField(_('Creation date'),auto_now_add=True)
    modifiedDate = models.DateTimeField(_('Last modified date'),auto_now=True)

    def __str__(self):
        return '%s: %s' % (_('FAQ'), self.question)

    class Meta:
        verbose_name = _('FAQ')
        verbose_name_plural = _('FAQs')
        ordering = ('orderNum',)


class FAQCategoryPluginModel(CMSPlugin):
    category = models.ForeignKey(FAQCategory,verbose_name=_('Category'))
    showTitle = models.BooleanField(verbose_name=_('Show Category Title'),default=False)

    def get_short_description(self):
        return self.category.name


class FAQSinglePluginModel(CMSPlugin):
    question = models.ForeignKey(FAQ,verbose_name=_('Question'))

    def get_short_description(self):
        return self.question
