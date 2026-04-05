from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
import logging

logger = logging.getLogger(__name__)


class PricingTier(models.Model):
    name = models.CharField(
        max_length=50, unique=True,
        help_text=_('Give this pricing tier a name (e.g. \'Default 4-week series\')')
    )

    # By default, prices may vary by online or door registration.
    # More sophisticated discounts, including student discounts
    # may be achieved through the discounts and vouchers apps, if enabled.
    onlinePrice = models.FloatField(
        _('Online price'), default=0, validators=[MinValueValidator(0)]
    )
    doorPrice = models.FloatField(
        _('At-the-door price'), default=0, validators=[MinValueValidator(0)]
    )

    dropinPrice = models.FloatField(
        _('Single class drop-in price'), default=0, validators=[MinValueValidator(0)],
        help_text=_('If students are allowed to drop in, then this price will be applied per class.')
    )

    expired = models.BooleanField(
        _('Expired'), default=False,
        help_text=_(
            "If this box is checked, then this pricing tier will not show up " +
            "as an option when creating new series.  Use this for old prices " +
            "or custom pricing that will not be repeated."
        )
    )

    def getBasePrice(self, **kwargs):
        '''
        This handles the logic of finding the correct price.  If more sophisticated
        discounting systems are needed, then this PricingTier model can be subclassed,
        or the discounts and vouchers apps can be used.
        '''
        payAtDoor = kwargs.get('payAtDoor', False)
        dropIns = kwargs.get('dropIns', 0)

        if dropIns:
            return dropIns * self.dropinPrice
        if payAtDoor:
            return self.doorPrice
        return self.onlinePrice

    # basePrice is the online registration price
    @property
    def basePrice(self):
        return self.onlinePrice
    basePrice.fget.short_description = _('Base price')

    def __str__(self):
        if self.expired:
            return '{} ({})'.format(self.name, str(_('expired')))
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Pricing tier')
        verbose_name_plural = _('Pricing tiers')
