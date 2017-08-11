from django.conf import settings
from django.utils import timezone


def ensure_timezone(dateTime,timeZone=None):
    '''
    Since this project is designed to be used in both time-zone aware
    and naive environments, this utility just returns a datetime as either
    aware or naive depending on whether time zone support is enabled.
    '''

    if timezone.is_aware(dateTime) and not getattr(settings,'USE_TZ',False):
        return timezone.make_naive(dateTime,timezone=timeZone)
    if timezone.is_naive(dateTime) and getattr(settings,'USE_TZ',False):
        return timezone.make_aware(dateTime,timezone=timeZone)
    # If neither condition is met, then we can return what was passed
    return dateTime
