from datetime import datetime
from urllib.parse import unquote

from .timezone import ensure_timezone


def getIntFromGet(request, key, allow_list=False, force_list=False):
    '''
    This function just parses the request GET data for the requested key,
    and returns it as an integer, returning none if the key is not
    available or is in incorrect format.
    '''

    # Allow lists to be returned only if the processs that called permits it.
    if force_list:
        allow_list = True

    value = request.GET.get(key)
    if not value:
        return None

    values = value.split(',')
    int_values = []
    for v in values:
        try:
            int_values.append(int(v))
        except (ValueError, TypeError):
            return None

    if len(int_values) == 1 and not force_list:
        return int_values[0]
    elif allow_list:
        return int_values


def getDateTimeFromGet(request, key):
    '''
    This function just parses the request GET data for the requested key,
    and returns it in datetime format, returning none if the key is not
    available or is in incorrect format.
    '''
    if request.GET.get(key, ''):
        try:
            return ensure_timezone(datetime.strptime(unquote(request.GET.get(key, '')), '%Y-%m-%d'))
        except (ValueError, TypeError):
            pass
    return None
