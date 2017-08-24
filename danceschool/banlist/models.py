from django.db import models
from django.utils.translation import ugettext_lazy as _
from filer.fields.image import FilerImageField
from jsonfield import JSONField


class BannedPerson(models.Model):

    firstName = models.CharField(_('First name'),max_length=30,)
    lastName = models.CharField(_('First name'),max_length=30,)

    photo = FilerImageField(verbose_name=_('Photo'),blank=True,null=True,related_name='banned_person_image')

    notes = models.TextField(_('Notes for internal purposes'),null=True,blank=True)

    expirationDate = models.DateTimeField(
        _('Expiration date'),
        null=True,blank=True,
        help_text=_('Leave blank for no expiration.')
    )

    disabled = models.BooleanField(
        _('Disabled'),
        help_text=_('<strong>Note:</strong>Checking this box will prevent this ban from being automatically enforced.'),
        default=False
    )

    def fullName(self):
        return ' '.join([self.firstName, self.lastName])

    class Meta:
        permissions = (('ignore_ban',_('Can register users despite banned credentials')),)

        ordering = ('lastName', 'firstName')
        verbose_name = _('Banned individual')
        verbose_name_plural = _('Banned individuals')


class BannedEmail(models.Model):
    person = models.ForeignKey(BannedPerson,verbose_name=_('Individual'))
    email = models.EmailField(_('Email address'), unique=True)

    class Meta:
        verbose_name = _('Banned email adddress')
        verbose_name_plural = _('Banned email addresses')


class BanFlaggedRecord(models.Model):
    person = models.ForeignKey(BannedPerson,verbose_name=_('Person'))
    dateTime = models.DateTimeField(_('Date and time'),auto_now_add=True)
    ipAddress = models.GenericIPAddressField(_('IP address'),null=True,blank=True)
    flagCode = models.CharField(_('Flag code'),max_length=8,help_text=_('Search for this code for easier reference.'))
    data = JSONField(_('Session and form data'),default={})

    class Meta:
        ordering = ('-dateTime',)
        verbose_name = _('Record of ban being flagged')
        verbose_name_plural = _('Records of bans being flagged')
