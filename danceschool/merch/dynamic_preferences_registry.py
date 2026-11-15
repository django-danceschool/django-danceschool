'''
This file defines preferences that must be set in the DB, but can be changed
dynamically.

The merch app currently defines no preferences of its own. The sales tax rate
for merchandise was formerly set here; it is now determined by the tax
jurisdiction of the at-the-door register through which an item is sold (or
the default tax jurisdiction for the site), and it can be overridden for an
individual merchandise item.
'''
