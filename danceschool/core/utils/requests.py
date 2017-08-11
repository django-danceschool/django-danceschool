from datetime import datetime
from urllib.parse import unquote

from .timezone import ensure_timezone


def getIntFromGet(request,key):
    '''
    This function just parses the request GET data for the requested key,
    and returns it as an integer, returning none if the key is not
    available or is in incorrect format.
    '''
    try:
        return int(request.GET.get(key))
    except (ValueError, TypeError):
        return None


def getDateTimeFromGet(request,key):
    '''
    This function just parses the request GET data for the requested key,
    and returns it in datetime format, returning none if the key is not
    available or is in incorrect format.
    '''
    if request.GET.get(key,''):
        try:
            return ensure_timezone(datetime.strptime(unquote(request.GET.get(key,'')),'%Y-%m-%d'))
        except (ValueError, TypeError):
            pass
    return None
