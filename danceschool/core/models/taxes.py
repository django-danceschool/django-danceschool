from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


def get_taxRuleItemTypes():
    '''
    Tax rules may be applied to any subclass of Event (class series, public
    events, private lessons, etc.), as well as to merchandise if the merch app
    is installed. This is used to limit the choices on TaxRule.itemType.
    '''
    from .event_base import Event

    limit = Q(pk__in=[])
    for model in apps.get_models():
        if issubclass(model, Event) and model is not Event:
            limit |= Q(app_label=model._meta.app_label, model=model._meta.model_name)
    if apps.is_installed('danceschool.merch'):
        limit |= Q(app_label='merch', model='merchitem')
    return limit


class TaxJurisdiction(models.Model):
    '''
    A tax jurisdiction is an authority to which sales tax (or a similar tax,
    such as an admissions tax) is owed. Depending on local rules, this may be
    a state, a county, or a city. Locations and at-the-door registers are
    assigned to jurisdictions, and each invoice item records the jurisdiction
    under which its tax was calculated.
    '''

    name = models.CharField(
        _('Name'), max_length=100, unique=True,
        help_text=_('The name of this jurisdiction, as used in reports.')
    )
    taxLabel = models.CharField(
        _('Tax label'), max_length=100, blank=True,
        help_text=_(
            'The name of the tax as it should be shown to customers ' +
            '(e.g. \'DC Sales Tax\'). If blank, the jurisdiction name is used.'
        )
    )
    defaultRate = models.FloatField(
        _('Default tax rate'), default=0, validators=[MinValueValidator(0)],
        help_text=_(
            'Enter as a whole number percentage (e.g. enter \'6\' for 6%). ' +
            'This rate applies to everything sold in this jurisdiction ' +
            'unless a more specific rule is defined below, or unless an ' +
            'individual event or merchandise item overrides it.'
        )
    )
    accountNumber = models.CharField(
        _('Account/filing number'), max_length=100, blank=True,
        help_text=_('Optional. Your registration number with this tax authority.')
    )
    notes = models.TextField(_('Notes'), blank=True)

    @property
    def label(self):
        return self.taxLabel or self.name

    def getRate(self, obj=None):
        '''
        Return the tax rate that applies in this jurisdiction to the passed
        object (an Event or a MerchItem). A rule for the object's category
        prevails over a rule for its type, which prevails over the default rate
        for the jurisdiction. Item-specific overrides are not handled here; use
        danceschool.core.utils.tax.getTaxRate() for that.

        TaxRule.clean() prevents more than one rule from applying at the same
        level, but that is not enforced by the database. If duplicates exist
        anyway, the highest of their rates is used, so that the result never
        depends on the order in which the rules are returned.
        '''
        if obj is None:
            return self.defaultRate

        ct_id = getattr(obj, 'polymorphic_ctype_id', None)
        if not ct_id:
            ct_id = ContentType.objects.get_for_model(type(obj)).id
        category_id = getattr(obj, 'category_id', None)

        category_rates = []
        type_rates = []
        for rule in self.taxrule_set.all():
            if rule.itemType_id != ct_id:
                continue
            if not rule.category_id:
                type_rates.append(rule.rate)
            elif rule.category_id == category_id:
                category_rates.append(rule.rate)

        if category_rates:
            return max(category_rates)
        if type_rates:
            return max(type_rates)
        return self.defaultRate

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Tax jurisdiction')
        verbose_name_plural = _('Tax jurisdictions')


class TaxRule(models.Model):
    '''
    A tax rule overrides the default rate of a tax jurisdiction for a specific
    type of item (e.g. all class series), or for a specific category of class
    series or public events.
    '''

    jurisdiction = models.ForeignKey(
        TaxJurisdiction, verbose_name=_('Tax jurisdiction'), on_delete=models.CASCADE
    )
    itemType = models.ForeignKey(
        ContentType, verbose_name=_('Applies to'), on_delete=models.CASCADE,
        limit_choices_to=get_taxRuleItemTypes, null=True, blank=True,
        help_text=_('May be left blank if a category is selected.')
    )
    seriesCategory = models.ForeignKey(
        'core.SeriesCategory', verbose_name=_('Series category'),
        null=True, blank=True, on_delete=models.CASCADE,
        help_text=_('Optionally, limit this rule to one category of class series.')
    )
    publicEventCategory = models.ForeignKey(
        'core.PublicEventCategory', verbose_name=_('Public event category'),
        null=True, blank=True, on_delete=models.CASCADE,
        help_text=_('Optionally, limit this rule to one category of public events.')
    )
    rate = models.FloatField(
        _('Tax rate'), default=0, validators=[MinValueValidator(0)],
        help_text=_(
            'Enter as a whole number percentage (e.g. enter \'6\' for 6%). ' +
            'Enter 0 if these items are exempt from tax in this jurisdiction.'
        )
    )

    @property
    def category_id(self):
        return self.seriesCategory_id or self.publicEventCategory_id

    def _categoryItemType(self):
        ''' The item type that is implied by the selected category, if any. '''
        from .event_types import Series, PublicEvent

        if self.seriesCategory_id:
            return ContentType.objects.get_for_model(Series)
        if self.publicEventCategory_id:
            return ContentType.objects.get_for_model(PublicEvent)

    def clean(self):
        if self.seriesCategory_id and self.publicEventCategory_id:
            raise ValidationError(_(
                'A tax rule may be limited to a series category or to a ' +
                'public event category, but not both.'
            ))

        implied = self._categoryItemType()
        if implied and self.itemType_id and self.itemType_id != implied.id:
            raise ValidationError(_(
                'The selected category does not match the type of item ' +
                'that this rule applies to.'
            ))
        if not implied and not self.itemType_id:
            raise ValidationError(_(
                'Select the type of item that this rule applies to.'
            ))

        if self.jurisdiction_id:
            duplicates = TaxRule.objects.filter(
                jurisdiction_id=self.jurisdiction_id,
                itemType_id=getattr(implied, 'id', None) or self.itemType_id,
                seriesCategory_id=self.seriesCategory_id,
                publicEventCategory_id=self.publicEventCategory_id,
            ).exclude(pk=self.pk)
            if duplicates.exists():
                raise ValidationError(_(
                    'This jurisdiction already has a rule for these items.'
                ))

    def save(self, *args, **kwargs):
        # A category rule always applies to the type of event that uses
        # that category.
        implied = self._categoryItemType()
        if implied:
            self.itemType = implied
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.seriesCategory or self.publicEventCategory or self.itemType
        return '%s: %s (%s%%)' % (self.jurisdiction, target, self.rate)

    class Meta:
        ordering = ('jurisdiction__name', 'itemType__model')
        verbose_name = _('Tax rule')
        verbose_name_plural = _('Tax rules')
