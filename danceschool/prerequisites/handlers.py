from django.dispatch import receiver
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from danceschool.core.signals import check_student_info
from danceschool.core.models import Series, Customer
from danceschool.core.constants import getConstant, REG_VALIDATION_STR

from .models import Requirement

import logging


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(check_student_info)
def checkRequirements(sender,**kwargs):
    '''
    Check that the customer meets all prerequisites for the items in the registration.
    '''

    if not getConstant('requirements__enableRequirements'):
        return

    logger.debug('Signal to check RegistrationContactForm handled by prerequisites app.')

    formData = kwargs.get('formData',{})
    first = formData.get('firstName')
    last = formData.get('lastName')
    email = formData.get('email')

    request = kwargs.get('request',{})
    session = getattr(request,'session',{}).get(REG_VALIDATION_STR,{})

    seriesinfo = session['regInfo'].get('events',{})
    seriesids = [int(k) for k,v in seriesinfo.items() if v.get('register',False)]
    seriess = Series.objects.filter(id__in=seriesids)

    customer = Customer.objects.filter(
        first_name=first,
        last_name=last,
        email=email).first()

    requirement_warnings = []
    requirement_errors = []

    for s in seriess:
        for req in s.getRequirements():
            if not req.customerMeetsRequirement(
                customer=customer,
                danceRole=seriesinfo.get(s.id,{}).get('role',None)
            ):
                if req.enforcementMethod == Requirement.EnforcementChoice.error:
                    requirement_errors.append((s.name, req.name))
                if req.enforcementMethod == Requirement.EnforcementChoice.warning:
                    requirement_warnings.append((s.name,req.name))

    if requirement_errors:
        raise ValidationError(format_html(
            '<p>{}</p> <ul>{}</ul> <p>{}</p>',
            ugettext('Unfortunately, you do not meet the following requirements/prerequisites for the items you have chosen:\n'),
            mark_safe(''.join(['<li><em>%s:</em> %s</li>\n' % x for x in requirement_errors])),
            getConstant('requirements__errorMessage') or '',
        ))

    if requirement_warnings:
        messages.warning(request,format_html(
            '<p>{}</p> <ul>{}</ul> <p>{}</p>',
            mark_safe(ugettext('<strong>Please Note:</strong> It appears that you do not meet the following requirements/prerequisites for the items you have chosen:\n')),
            mark_safe(''.join(['<li><em>%s:</em> %s</li>\n' % x for x in requirement_warnings])),
            getConstant('requirements__warningMessage') or '',
        ))
