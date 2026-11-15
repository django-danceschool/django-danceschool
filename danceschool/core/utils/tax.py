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
