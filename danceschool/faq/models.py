from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from cms.models.pluginmodel import CMSPlugin

from djangocms_text_ckeditor.fields import HTMLField


@python_2_unicode_compatible
class FAQCategory(models.Model):

    name = models.CharField(max_length=200,unique=True)

    # This defines the order number on the FAQ page
    orderNum = models.PositiveIntegerField(help_text=_('This number specifies the order in which categories will be shown.'), default=0)

    def __str__(self):
        return '%s: %s' % (_('FAQ Category'),self.name)

    class Meta:
        ordering = ('orderNum',)
        verbose_name_plural = _('FAQ Categories')


@python_2_unicode_compatible
class FAQ(models.Model):

    category = models.ForeignKey(FAQCategory,null=True)

    question = models.CharField(max_length=200)
    answer = HTMLField(help_text=_('Answer the question.'))

    # This defines the order number on the FAQ page
    orderNum = models.PositiveIntegerField(help_text=_('This number specifies the order in which the questions will be shown on the FAQ page.'), default=0)

    draft = models.BooleanField(default=False, help_text=_('Check this box to prevent publication.'))

    creationDate = models.DateTimeField(auto_now_add=True)
    modifiedDate = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '%s: %s' % (_('FAQ'), self.question)

    class Meta:
        ordering = ('orderNum',)


class FAQCategoryPluginModel(CMSPlugin):
    category = models.ForeignKey(FAQCategory)
    showTitle = models.BooleanField(verbose_name=_('Show Category Title'),default=False)


class FAQSinglePluginModel(CMSPlugin):
    question = models.ForeignKey(FAQ)
