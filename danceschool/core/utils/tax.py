'''
Sales tax resolution. All code that needs to know which tax rate and tax
jurisdiction apply to something that is being sold should use these functions,
so that the rules are applied the same way everywhere.

The site-wide default jurisdiction (the registration__defaultTaxJurisdiction
preference) is used whenever an item has no jurisdiction of its own, such as
an event with no location. If that preference is not set, then there is no
jurisdiction and no tax is applied.
'''
from ..constants import getConstant


def getTaxRate(obj, jurisdiction):
    '''
    Return the tax rate (as a percentage) that applies to the passed Event or
    MerchItem in the passed jurisdiction. An override on the item itself always
    prevails (including an override of 0, which makes the item exempt).
    Otherwise, the rules of the jurisdiction apply. If there is no jurisdiction,
    then no tax is applied.
    '''
    override = getattr(obj, 'taxRateOverride', None)
    if override is not None:
        return override
    if not jurisdiction:
        return 0
    return jurisdiction.getRate(obj) or 0


def getEventTax(event):
    '''
    Return a tuple of (rate, jurisdiction) for a registration to the passed
    event. Events are taxed based on the location in which they take place.
    '''
    location = getattr(event, 'location', None)
    jurisdiction = (
        getattr(location, 'taxJurisdiction', None) or
        getConstant('registration__defaultTaxJurisdiction')
    )
    return getTaxRate(event, jurisdiction), jurisdiction


def getItemTax(obj, jurisdiction=None):
    '''
    Return a tuple of (rate, jurisdiction) for the sale of something that has
    no location of its own (e.g. merchandise). The caller passes the
    jurisdiction of the point of sale, if it is known.
    '''
    jurisdiction = jurisdiction or getConstant('registration__defaultTaxJurisdiction')
    return getTaxRate(obj, jurisdiction), jurisdiction


# Refunds
#
# The tax on an item is the same fraction of each dollar that is paid for it,
# so the same fraction of a refund of the item is tax that is refunded.  When
# the buyer pays sales tax, the amount paid is the total plus the tax.  When
# the seller pays it, the tax is included in the total.  The tax on an item is
# not changed by a refund (it is the tax on the sale), so the tax that is
# refunded is subtracted wherever the tax owed or net revenue is reported.
# These functions are used for invoice items and for revenue items, which
# have the same fields.


def getRefundedTaxes(refunds, total, taxes, buyerPaysSalesTax):
    ''' The tax that is included in the passed refunds of an item. '''
    paid = (total or 0) + ((taxes or 0) if buyerPaysSalesTax else 0)
    if not refunds or not taxes or paid <= 0:
        return 0
    return refunds * taxes / paid


def refundedTaxesExpression(buyer_pays='buyerPaysSalesTax'):
    '''
    A database expression for getRefundedTaxes(), for a model with refunds,
    total and taxes fields.  The buyer_pays argument names the field that says
    whether the buyer pays sales tax (e.g. on the related invoice).
    '''
    from django.db.models import Case, F, FloatField, Q, Value, When
    from django.db.models.functions import Coalesce, NullIf

    paid = Case(
        When(Q(**{buyer_pays: True}), then=F('total') + F('taxes')),
        default=F('total'), output_field=FloatField(),
    )
    return Coalesce(
        F('refunds') * F('taxes') / NullIf(paid, Value(0.0)),
        Value(0.0), output_field=FloatField(),
    )


def netRevenueExpression(buyer_pays='buyerPaysSalesTax'):
    '''
    A database expression for the net revenue of an invoice item or revenue
    item: what was paid for it and kept, less fees, and less any sales tax
    that is owed on it.
    '''
    from django.db.models import Case, F, FloatField, Q, Value, When

    return (
        F('total') + F('adjustments') - F('fees') - F('refunds') +
        refundedTaxesExpression(buyer_pays) -
        Case(
            When(Q(**{buyer_pays: False}), then=F('taxes')),
            default=Value(0.0), output_field=FloatField(),
        )
    )


def getNetRevenue(total, adjustments, fees, refunds, taxes, buyerPaysSalesTax, refundedTaxes=None):
    ''' The same as netRevenueExpression(), for values that have been loaded. '''
    if refundedTaxes is None:
        refundedTaxes = getRefundedTaxes(refunds, total, taxes, buyerPaysSalesTax)
    net = (total or 0) + (adjustments or 0) - (fees or 0) - (refunds or 0) + refundedTaxes
    if not buyerPaysSalesTax:
        net -= (taxes or 0)
    return net
