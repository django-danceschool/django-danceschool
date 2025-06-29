# This module just provides a faster way to access the Square client for this
# installation.
from django.conf import settings
from django.utils import timezone

from datetime import datetime
from datetime import timezone as tz

from square import Square
from square.environment import SquareEnvironment

api_environment = (
    SquareEnvironment.PRODUCTION if 'production' in
    str(getattr(settings, 'SQUARE_ENVIRONMENT', 'sandbox')).lower()
    else SquareEnvironment.SANDBOX
)
# The token is provided with a placeholder to avoid issues with blank bearer
# tokens. However, this must be specified in settings or Square cannot work.
api_client = Square(
    token=getattr(settings, 'SQUARE_ACCESS_TOKEN', 'django-danceschool'),
    environment=api_environment
)


def iso_timestamp_to_localtime(timestamp):
    '''
    Convert the ISO string timestamps that the Square API provides into a
    localized datetime.
    '''
    iso_formats = [
        ('%Y-%m-%dT%H:%M:%S.%fZ', tz.utc),
        ('%Y-%m-%dT%H:%M:%SZ', tz.utc),
        ('%Y-%m-%d', timezone.get_default_timezone()),
    ]
    dt = None

    for format in iso_formats:
        try:
            dt = datetime.strptime(
                timestamp, format[0]
            ).replace(tzinfo=format[1])
        except (TypeError, ValueError):
            continue
    if dt:
        return timezone.template_localtime(dt)
