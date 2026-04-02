from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from danceschool.core.models import StaffMember, Location


class TransactionParty(models.Model):
    '''
    An expense can be directly associated with a User or StaffMember (like an instructor),
    a location, or the name of another party.  Similarly, a revenue item can be received
    from different types of parties.
    '''

    name = models.CharField(_('Name'), max_length=50, null=True, blank=True)
    user = models.OneToOneField(
        User, null=True, blank=True,
        verbose_name=_('User'),
        on_delete=models.SET_NULL
    )
    staffMember = models.OneToOneField(
        StaffMember, null=True, blank=True,
        verbose_name=_('Staff member'),
        on_delete=models.SET_NULL
    )
    location = models.OneToOneField(
        Location, null=True, blank=True,
        verbose_name=_('Location'),
        on_delete=models.SET_NULL
    )

    def clean(self):
        '''
        Verify that the user and staffMember are not mismatched.
        Location can only be specified if user and staffMember are not.
        '''

        if (
            self.staffMember and self.staffMember.userAccount and
            self.user and not self.staffMember.userAccount == self.user
        ):
            raise ValidationError(_('Transaction party user does not match staff member user.'))

        if self.location and (self.user or self.staffMember):
            raise ValidationError(_(
                'Transaction party may not be both a Location and a User or StaffMember.'
            ))

    def save(self, updateBy=None, *args, **kwargs):
        '''
        Verify that the user and staffMember are populated with linked information, and
        ensure that the name is properly specified.
        '''

        if (
            self.staffMember and self.staffMember.userAccount and not self.user
        ) or (
            isinstance(updateBy, StaffMember) and self.staffMember.userAccount
        ):
            self.user = self.staffMember.userAccount
        elif (
            self.user and getattr(self.user, 'staffmember', None) and not self.staffMember
        ) or (
            isinstance(updateBy, User) and getattr(self.user, 'staffmember', None)
        ):
            self.staffMember = self.user.staffmember

        # Don't replace the name if it has been given, but do fill it out if it is blank.
        if not self.name:
            if self.user and self.user.get_full_name():
                self.name = self.user.get_full_name()
            elif self.staffMember:
                self.name = self.staffMember.fullName or self.staffMember.privateEmail
            elif self.location:
                self.name = self.location.name

        super().save(*args, **kwargs)

    def __str__(self):
        if self.name:
            return self.name
        elif self.user:
            return self.user.get_full_name()
        elif self.staffMember:
            return self.staffMember.fullName
        elif self.location:
            return self.location.name
        else:
            return str(_('Unspecified'))

    class Meta:
        ordering = ['name', ]
        verbose_name = _('Transaction party')
        verbose_name_plural = _('Transaction parties')

        permissions = (
            (
                'can_autocomplete_transactionparty',
                _('Able to use transaction party autocomplete features (in admin forms)')
            ),
        )

        constraints = [
            models.CheckConstraint(
                check=(
                    Q(name__isnull=False) | Q(user__isnull=False) |
                    Q(staffMember__isnull=False) | Q(location__isnull=False)
                ),
                name='must_specify_party'
            ),
        ]
