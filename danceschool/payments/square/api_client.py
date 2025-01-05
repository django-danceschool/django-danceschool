# This module just provides a faster way to access the Square client for this
# installation.
from django.conf import settings

from square.client import Client

api_client = Client(
    access_token=getattr(settings, 'SQUARE_ACCESS_TOKEN', ''),
    environment=getattr(settings, 'SQUARE_ENVIRONMENT', 'production')
)
