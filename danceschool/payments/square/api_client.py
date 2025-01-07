# This module just provides a faster way to access the Square client for this
# installation.
from django.conf import settings
from django.utils import timezone

from datetime import datetime
from datetime import timezone as tz

from square.client import Client


api_client = Client(
    access_token=getattr(settings, 'SQUARE_ACCESS_TOKEN', ''),
    environment=getattr(settings, 'SQUARE_ENVIRONMENT', 'production')
)


def iso_timestamp_to_localtime(timestamp):
    '''
    Convert the ISO string timestamps that the Square API provides into a
    localized datetime.
    '''
    try:
        dt = datetime.strptime(
            timestamp, '%Y-%m-%dT%H:%M:%S.%fZ'
        ).replace(tzinfo=tz.utc)
    except ValueError:
        return None

    return timezone.template_localtime(dt)
