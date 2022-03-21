from django import template

from danceschool.financial.models import ExpenseItem, RevenueItem

# This is needed to register all the tags
register = template.Library()


@register.simple_tag(takes_context=True)
def getAllocation(context, item, property):
    if not (isinstance(item, ExpenseItem) or isinstance(item, RevenueItem)):
        return None
    basis = context.get('allocationBasis', {})
    return "{:.2f}".format(item.getAllocation(**basis) * getattr(item, property, 0))

@register.simple_tag(takes_context=True)
def getAllocatedSum(context, items, property):
    basis = context.get('allocationBasis', {})
    return "{:.2f}".format(
        sum([
            item.getAllocation(**basis) * getattr(item, property, 0)
            for item in items
        ])
    )
