from django import forms as django_forms
from django.dispatch import receiver
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy as _
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe

from crispy_forms.layout import Field

from danceschool.core.signals import check_student_info, collect_student_info_fields
from danceschool.core.models import Customer, Registration
from danceschool.core.constants import getConstant

from .models import Requirement

import logging


# Define logger for this file
logger = logging.getLogger(__name__)


@receiver(collect_student_info_fields)
def addPrerequisiteAcknowledgement(sender, **kwargs):
    '''
    If any EventRegistrations in the current registration have requirements
    with enforcementMethod == 'acknowledgement', inject a mandatory checkbox
    into RegistrationContactForm asking the customer to confirm they meet
    those prerequisites.

    The checkbox label contains a tooltip link that lists the specific
    prerequisite names and the events they apply to, so the customer can
    see exactly what they are agreeing to.

    Returns a list with one (field_name, field, layout_element) tuple when
    acknowledgement requirements are found, otherwise returns None.
    '''
    if not getConstant('requirements__enableRequirements'):
        return None

    eventRegs = kwargs.get('eventRegs', [])

    # Collect (event_name, requirement_name) pairs for acknowledgement reqs only.
    items = []
    for ter in eventRegs:
        if hasattr(ter.event, 'getRequirements'):
            for req in ter.event.getRequirements():
                if req.enforcementMethod == Requirement.EnforcementChoice.acknowledgement:
                    items.append((ter.event.name, req.name))

    if not items:
        return None

    # Build the tooltip HTML content.  Each item's text is escaped for safe
    # HTML display; the whole string is left as a plain (non-safe) Python str
    # so that format_html will attribute-escape it when placing it in title="".
    tooltip_lines = ['<ul>']
    for event_name, req_name in items:
        tooltip_lines.append(
            '<li><em>%s</em>: %s</li>' % (escape(event_name), escape(req_name))
        )
    tooltip_lines.append('</ul>')
    tooltip_html = ''.join(tooltip_lines)

    label = format_html(
        '{} <a tabindex="0" role="button" data-toggle="tooltip" data-html="true" '
        'data-placement="top" title="{}" style="cursor:pointer;">[{}]</a>',
        _('I confirm that I meet the prerequisites for the classes I have registered for'),
        tooltip_html,
        _('details'),
    )

    field_name = 'acknowledge_prerequisites'
    field = django_forms.BooleanField(required=True, label=mark_safe(label))
    layout_element = Field(field_name)

    return [(field_name, field, layout_element)]


@receiver(check_student_info)
def checkRequirements(sender, **kwargs):
    '''
    Check that the customer meets all prerequisites for the items in the registration.
    '''

    if not getConstant('requirements__enableRequirements'):
        return

    logger.debug('Signal to check RegistrationContactForm handled by prerequisites app.')

    formData = kwargs.get('data', {})
    first = formData.get('firstName')
    last = formData.get('lastName')
    email = formData.get('email')

    request = kwargs.get('request', {})

    registration = kwargs.get('registration', None)
    if not registration:
        invoice = kwargs.get('invoice', None)
        registration = Registration.objects.filter(invoice=invoice).first()
    if not registration:
        return

    eventRegs = kwargs.get('eventRegs', [])

    customer = Customer.objects.filter(
        first_name=first,
        last_name=last,
        email=email).first()

    requirement_warnings = []
    requirement_errors = []

    for ter in eventRegs:
        if hasattr(ter.event, 'getRequirements'):
            for req in ter.event.getRequirements():
                if not req.customerMeetsRequirement(
                    customer=customer,
                    danceRole=ter.role
                ):
                    if req.enforcementMethod == Requirement.EnforcementChoice.error:
                        requirement_errors.append((ter.event.name, req.name))
                    if req.enforcementMethod == Requirement.EnforcementChoice.warning:
                        requirement_warnings.append((ter.event.name, req.name))

    if requirement_errors:
        raise ValidationError(format_html(
            '<p>{}</p> <ul>{}</ul> <p>{}</p>',
            gettext(
                'Unfortunately, you do not meet the following ' +
                'requirements/prerequisites for the items you have chosen:\n'
            ),
            mark_safe(''.join(['<li><em>%s:</em> %s</li>\n' % x for x in requirement_errors])),
            getConstant('requirements__errorMessage') or '',
        ))

    if requirement_warnings:
        messages.warning(request, format_html(
            '<p>{}</p> <ul>{}</ul> <p>{}</p>',
            mark_safe(gettext(
                '<strong>Please Note:</strong> It appears that you do not ' +
                'meet the following requirements/prerequisites for the items ' +
                'you have chosen:\n'
            )),
            mark_safe(''.join(['<li><em>%s:</em> %s</li>\n' % x for x in requirement_warnings])),
            getConstant('requirements__warningMessage') or '',
        ))
