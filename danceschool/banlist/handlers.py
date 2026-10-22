# Python Imports
import logging
import string
import random

# Third Party Imports
from django.dispatch import receiver
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, gettext
from django.db.models import Q

# Local Application Specific Imports
from danceschool.banlist.models import BannedPerson, BanFlaggedRecord
from danceschool.core.signals import check_student_info
from danceschool.core.constants import getConstant, REG_VALIDATION_STR
from danceschool.core.tasks import sendEmail
from danceschool.core.models import Registration

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

    formData = kwargs.get('data', {})
    first = formData.get('firstName')
    last = formData.get('lastName')
    email = formData.get('email')

    request = kwargs.get('request', {})
    session = getattr(request, 'session', {}).get(REG_VALIDATION_STR, {})
    payAtDoor = session.get('payAtDoor', False)
    registrationId = getattr(kwargs.get('registration', None), 'id', None)
    invoice = kwargs.get('invoice', None)
    invoiceId = str(getattr(invoice, 'id', ''))

    if not registrationId and invoice:
        registrationId = getattr(
            Registration.objects.filter(invoice=invoice).first(), 'id', None
        )

    # Only match on values that were actually provided.  A missing value must
    # never be passed to an iexact lookup, because Django treats iexact=None as
    # "IS NULL", which would match every banned person with no email addresses.
    # (A missing value is common here: fields that fail validation are absent
    # from the form's cleaned_data, but clean() still sends this signal.)
    first = (first or '').strip()
    last = (last or '').strip()
    email = (email or '').strip()

    match_query = Q()
    if first and last:
        match_query |= Q(firstName__iexact=first) & Q(lastName__iexact=last)
    if email:
        match_query |= Q(bannedemail__email__iexact=email)

    if not match_query:
        return

    records = BannedPerson.objects.exclude(
        disabled=True
    ).exclude(
        expirationDate__lte=timezone.now()
    ).filter(match_query).distinct()

    if not records.exists():
        return

    # Generate an "error code" to reference so that it is easier to lookup
    # the record on why they were flagged.
    flagCode = ''.join(random.choice(string.ascii_uppercase) for x in range(8))
    ip = get_client_ip(request)
    respondTo = getConstant('registration__banListContactEmail') or getConstant('contact__businessEmail')

    flagRecords = []
    for record in records:
        flagRecords.append(BanFlaggedRecord.objects.create(
            flagCode=flagCode,
            person=record,
            ipAddress=ip,
            data={
                'session': session, 'formData': formData,
                'registrationId': registrationId, 'invoiceId': invoiceId,
            }
        ))

    notify = getConstant('registration__banListNotificationEmail')
    if notify:
        send_from = getConstant('contact__businessEmail')
        subject = _('Notice of attempted registration by banned individual')

        # Report every matched individual and what they were matched on.
        matches = []
        for record in records:
            reasons = []
            if first and last and (
                record.firstName.lower() == first.lower() and
                record.lastName.lower() == last.lower()
            ):
                reasons.append(gettext('name'))
            if email and email.lower() in [x.lower() for x in record.relatedEmails]:
                reasons.append(gettext('email'))
            matches.append('%s (matched on %s)' % (record.fullName, ', '.join(reasons)))

        message = _(
            'This is an automated notification that an individual matching the following ' +
            'banned individual(s) has attempted to register for a class series or event:\n\n' +
            'Banned individual(s): %s\n' % '; '.join(matches) +
            'Submitted name: %s %s\n' % (first, last) +
            'Submitted email: %s\n' % email +
            'Date/Time: %s\n' % flagRecords[-1].dateTime +
            'IP Address: %s\n\n' % ip +
            'This individual has been prevented from finalizing their registration, and they ' +
            'have been asked to notify the school at %s with code %s to proceed.' % (respondTo, flagCode)
        )

        sendEmail(subject, message, send_from, to=[notify])

    message = format_html(
        '<strong>{}:</strong> {}', gettext('ERROR'),
        (
            getConstant('registration__banListDoorNotificationText')
            if payAtDoor else
            getConstant('registration__banListNotificationText')
        ).format(respondTo=respondTo, flagCode=flagCode)
    )

    if request.user.has_perm('banlist.ignore_ban'):
        messages.error(request, message, extra_tags='banlist_found')
        messages.warning(
            request,
            gettext(
                'Based on your permissions level, you are not prevented from '
                'proceeding with registration. However, completing this '
                'registration is not advised.'
            ), extra_tags='banlist_allow_proceed'
        )

    else:
        raise ValidationError(message)
