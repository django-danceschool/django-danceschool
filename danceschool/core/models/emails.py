from django.db import models
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from djangocms_text.fields import HTMLField
import logging

from ..constants import getConstant
from ..utils.emails import get_text_for_html

logger = logging.getLogger(__name__)


def get_defaultEmailName():
    ''' Callable for default used by EmailTemplate class '''
    return getConstant('email__defaultEmailName')


def get_defaultEmailFrom():
    ''' Callable for default used by EmailTemplate class '''
    return getConstant('email__defaultEmailFrom')


class EmailTemplate(models.Model):
    name = models.CharField(_('Template name'), max_length=100, unique=True)
    subject = models.CharField(_('Subject line'), max_length=200, null=True, blank=True)

    RICH_TEXT_CHOICES = (('plain', _('Plain text email')), ('HTML', _('HTML rich text email')))

    richTextChoice = models.CharField(
        _('Send this email as'), max_length=5,
        choices=RICH_TEXT_CHOICES, default='plain'
    )

    content = models.TextField(
        _('Plain text Content'), null=True, blank=True,
        help_text=_(
            'See the list of available variables for details on what ' +
            'information can be included with template tags.'
        )
    )
    html_content = HTMLField(
        _('HTML rich text content'), null=True, blank=True,
        help_text=_(
            'Emails are sent as plain text by default.  To send an HTML email ' +
            'instead, enter your desired content in this field.'
        )
    )

    defaultFromName = models.CharField(
        _('From name (default)'), max_length=100, null=True,
        blank=True, default=get_defaultEmailName
    )
    defaultFromAddress = models.EmailField(
        _('From address (default)'), max_length=100, null=True, blank=True,
        default=get_defaultEmailFrom
    )
    defaultCC = models.CharField(_('CC (default)'), max_length=100, null=True, blank=True)

    groupRequired = models.ForeignKey(
        Group, verbose_name=_('Group permissions required to use.'),
        null=True, blank=True,
        help_text=_('Some templates should only be visible to some users.'),
        on_delete=models.SET_NULL
    )
    hideFromForm = models.BooleanField(
        _('Hide from \'Email Students\' form'), default=False,
        help_text=_('Check this box for templates that are used for automated emails.')
    )

    @property
    def send_html(self):
        return (self.richTextChoice == 'HTML')
    send_html.fget.short_description = _('HTML Email Template')

    def save(self, *args, **kwargs):
        '''
        If this is an HTML template, then set the non-HTML content to be the
        stripped version of the HTML. If this is a plain text template, then
        set the HTML content to be null.
        '''
        if self.send_html:
            self.content = get_text_for_html(self.html_content)
        else:
            self.html_content = None

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Email template')
        verbose_name_plural = _('Email templates')
        permissions = (
            ('send_email', _('Can send emails using the SendEmailView')),
        )
