from django.contrib import admin

from ..models import PricingTier


@admin.register(PricingTier)
class PricingTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'expired')
    list_filter = ('expired', )

    # Need to specify an empty list of inlines so that discounts app can
    # add to the list if it is enabled.
    inlines = []
