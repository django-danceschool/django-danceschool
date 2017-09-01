from django.conf import settings
from django.utils.timezone import make_naive, make_aware, is_naive, is_aware, localtime


def ensure_timezone(dateTime,timeZone=None):
    '''
    Since this project is designed to be used in both time-zone aware
    and naive environments, this utility just returns a datetime as either
    aware or naive depending on whether time zone support is enabled.
    '''

    if is_aware(dateTime) and not getattr(settings,'USE_TZ',False):
        return make_naive(dateTime,timezone=timeZone)
    if is_naive(dateTime) and getattr(settings,'USE_TZ',False):
        return make_aware(dateTime,timezone=timeZone)
    # If neither condition is met, then we can return what was passed
    return dateTime


def ensure_localtime(dateTime):

    if not getattr(settings,'USE_TZ',False):
        return make_naive(dateTime) if is_aware(dateTime) else dateTime
    else:
        return localtime(make_aware(dateTime) if is_naive(dateTime) else dateTime)
