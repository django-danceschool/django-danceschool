from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ..models import TaxJurisdiction, TaxRule


class TaxRuleInline(admin.TabularInline):
    model = TaxRule
    extra = 0
    fields = ('itemType', 'seriesCategory', 'publicEventCategory', 'rate')
    verbose_name = _('Rule overriding the default rate')
    verbose_name_plural = _('Rules overriding the default rate')


@admin.register(TaxJurisdiction)
class TaxJurisdictionAdmin(admin.ModelAdmin):
    inlines = [TaxRuleInline, ]

    list_display = ('name', 'taxLabel', 'defaultRate', 'numRules', 'accountNumber')
    search_fields = ('name', 'taxLabel', 'accountNumber')

    fields = ('name', 'taxLabel', 'defaultRate', 'accountNumber', 'notes')

    @admin.display(description=_('# Rules'))
    def numRules(self, obj):
        return obj.taxrule_set.count()
