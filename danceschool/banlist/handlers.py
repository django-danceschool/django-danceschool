from django.dispatch import receiver
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import ugettext
from django.db.models import Q

from danceschool.core.signals import check_student_info
from danceschool.core.constants import getConstant, REG_VALIDATION_STR

from .models import BannedPerson, BanFlaggedRecord

import logging
import string
import random

# Define logger for this file
logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@receiver(check_student_info)
def checkBanlist(sender,**kwargs):
    '''
    Check that this individual is not on the ban list.
    '''

    if not getConstant('registration__enableBanList'):
        return

    logger.debug('Signal to check RegistrationContactForm handled by banlist app.')

    formData = kwargs.get('formData',{})
    first = formData.get('firstName')
    last = formData.get('lastName')
    email = formData.get('email')

    request = kwargs.get('request',{})
    session = getattr(request,'session',{}).get(REG_VALIDATION_STR,{})

    records = BannedPerson.objects.exclude(
        disabled=True
    ).exclude(
        expirationDate__lte=timezone.now()
    ).filter(
        (Q(firstName__iexact=first) & Q(lastName__iexact=last)) |
        Q(bannedemail__email__iexact=email)
    )

    if not records.exists():
        return

    # Generate an "error code" to reference so that it is easier to lookup
    # the record on why they were flagged.
    flagCode = ''.join(random.choice(string.ascii_uppercase) for x in range(8))

    for record in records:
        BanFlaggedRecord.objects.create(
            flagCode=flagCode,
            person=record,
            ipAddress=get_client_ip(request),
            data={'session': session, 'formData': formData,}
        )

    message = ugettext('There appears to be an issue with this registration.  Please contact %s to proceed with the registration process.  You may reference the error code %s.' % (getConstant('registration__banListContactEmail'), flagCode))

    if request.user.has_perm('banlist.ignore_ban'):
        messages.warning(request, message)

    else:
        raise ValidationError(message)
