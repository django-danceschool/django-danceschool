from django.conf import settings
from django.utils.translation import ugettext_lazy as _


CAROUSEL_PAUSE_CHOICES = (
    ('hover', 'hover'),
    ('mouseenter', 'mouseenter'),
    ('mouseleave', 'mouseleave'),
    ('false', 'off'),
)

CAROUSEL_RIDE_CHOICES = (
    ('carousel', 'carousel'),
    ('false', 'off'),
)

# this is used when no valua is passed in the template via
# {% with 1024 as width and 768 as height %}
CAROUSEL_DEFAULT_SIZE = [1024, 768]

CAROUSEL_ASPECT_RATIOS = (
    (1, 1),
    (3, 2),
    (4, 3),
    (21, 9),
    (18, 9),
)

CAROUSEL_ASPECT_RATIO_CHOICES = (
    tuple([
        ('{0}x{1}'.format(x, y), '{0}x{1}'.format(x, y))
        for x, y in CAROUSEL_ASPECT_RATIOS
    ])
)

# The default grid size for Bootstrap 4 is 12. You can change this setting
# to whatever layout you require. We suggest that the value is at
# least devisable by 2, 3 and 4.
GRID_SIZE = getattr(
    settings,
    'DJANGOCMS_BOOTSTRAP4_GRID_SIZE',
    12,
)

GRID_COLUMN_CHOICES = getattr(
    settings,
    'DJANGOCMS_BOOTSTRAP4_GRID_COLUMN_CHOICES',
    (
        ('col', _('Column')),
        ('w-100', _('Break')),
        ('', _('Empty'))
    ),
)

DEVICE_CHOICES = (
    ('xs', _('Extra small')),   # default <576px
    ('sm', _('Small')),         # default ≥576px
    ('md', _('Medium')),        # default ≥768px
    ('lg', _('Large')),         # default ≥992px
    ('xl', _('Extra large')),   # default ≥1200px
)
DEVICE_SIZES = tuple([size for size, name in DEVICE_CHOICES])
