# Python Imports
import logging
import string
import random

# Third Party Imports
from django.dispatch import receiver
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import ugettext
from django.utils.translation import ugettext_lazy as _
from django.db.models import Q

# Local Application Specific Imports
from danceschool.banlist.models import BannedPerson, BanFlaggedRecord
from danceschool.core.signals import check_student_info
from danceschool.core.constants import getConstant, REG_VALIDATION_STR
from danceschool.core.tasks import sendEmail

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
def checkBanlist(sender, **kwargs):
    '''
    Check that this individual is not on the ban list.
    '''

    if not getConstant('registration__enableBanList'):
        return

    logger.debug('Signal to check RegistrationContactForm handled by banlist app.')

    formData = kwargs.get('formData', {})
    first = formData.get('firstName')
    last = formData.get('lastName')
    email = formData.get('email')

    request = kwargs.get('request', {})
    session = getattr(request, 'session', {}).get(REG_VALIDATION_STR, {})
    registrationId = getattr(kwargs.get('registration', None), 'id', None)

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
    ip = get_client_ip(request)
    respondTo = getConstant('registration__banListContactEmail') or getConstant('contact__businessEmail')

    for record in records:
        flagRecord = BanFlaggedRecord.objects.create(
            flagCode=flagCode,
            person=record,
            ipAddress=ip,
            data={'session': session, 'formData': formData, 'registrationId': registrationId}
        )

    notify = getConstant('registration__banListNotificationEmail')
    if notify:
        send_from = getConstant('contact__businessEmail')
        subject = _('Notice of attempted registration by banned individual')
        message = _(
            'This is an automated notification that the following individual has attempted ' +
            'to register for a class series or event:\n\n' +
            'Name: %s\n' % record.fullName +
            'Email: %s\n' % email +
            'Date/Time: %s\n' % flagRecord.dateTime +
            'IP Address: %s\n\n' % ip +
            'This individual has been prevented from finalizing their registration, and they ' +
            'have been asked to notify the school at %s with code %s to proceed.' % (respondTo, flagCode)
        )

        sendEmail(subject, message, send_from, to=[notify])

    message = ugettext('There appears to be an issue with this registration. '
                       'Please contact %s to proceed with the registration process. '
                       'You may reference the error code %s.' % (respondTo, flagCode))

    if request.user.has_perm('banlist.ignore_ban'):
        messages.warning(request, message)

    else:
        raise ValidationError(message)
