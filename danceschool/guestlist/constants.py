from django.utils.translation import ugettext_lazy as _


GUESTLIST_ADMISSION_CHOICES = [
    ('Always',_('Always added to guest list')),
    ('EventOnly',_('Add if the person is a staff member for this event')),
    ('Day',_('Add if the person is a staff member on that day')),
    ('Week',_('Add if the person is a staff member in that week')),
    ('Month',_('Add if the person is a staff member in that month')),
    ('Year',_('Add if the person is a staff member in that year')),
]


GUESTLIST_SORT_CHOICES = [
    ('Last',_('Last name (default)')),
    ('First',_('First name')),
    ('Comp',_('Admission type (e.g. staff, registrant, other')),
]
