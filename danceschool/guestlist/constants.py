from django.utils.translation import gettext_lazy as _


GUESTLIST_ADMISSION_CHOICES = [
    ('Always', _('Always added to guest list')),
    ('EventOnly', _('Add if the person is a staff member for this event')),
    ('Day', _('Add if the person is a staff member on that day')),
    ('Week', _('Add if the person is a staff member in that week')),
    ('Month', _('Add if the person is a staff member in that month')),
    ('Year', _('Add if the person is a staff member in that year')),
    ('Rolling', _('Add if the person is a staff member within a specified number of days')),
]


GUESTLIST_REGISTRATION_ADMISSION_CHOICES = [
    ('Day', _('Add if the person is registered for a qualifying event on that day')),
    ('Week', _('Add if the person is registered for a qualifying event in that week')),
    ('Month', _('Add if the person is registered for a qualifying event in that month')),
    ('Year', _('Add if the person is registered for a qualifying event in that year')),
    (
        'Rolling',
        _('Add if the person is registered for a qualifying event within a specified number of days')
    ),
]


GUESTLIST_SORT_CHOICES = [
    ('Last', _('Last name (default)')),
    ('First', _('First name')),
    ('Comp', _('Admission type (e.g. staff, registrant, other')),
]
