from django import forms as django_forms
from django.dispatch import receiver
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy as _
from django.utils.html import format_html, format_html_join
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

    The specific prerequisite names and the events they apply to are listed
    beneath the checkbox, so the customer can see exactly what they are
    agreeing to.

    Returns a list with one (field_name, field, layout_element) tuple when
    acknowledgement requirements are found, otherwise returns None.
    '''
    if not getConstant('requirements__enableRequirements'):
        return None

    eventRegs = kwargs.get('eventRegs', [])

    # Collect the acknowledgement requirements for each event, in order,
    # as {event pk: (event name, [requirement names])}.
    events = {}
    for ter in eventRegs:
        if hasattr(ter.event, 'getRequirements'):
            for req in ter.event.getRequirements():
                if req.enforcementMethod == Requirement.EnforcementChoice.acknowledgement:
                    names = events.setdefault(ter.event.pk, (ter.event.name, []))[1]
                    if req.name not in names:
                        names.append(req.name)

    if not events:
        return None

    # List the specific prerequisites beneath the checkbox (as the field's
    # help text), with a heading for each class and a bullet for each of its
    # prerequisites, so that the customer can see exactly what they are
    # agreeing to without having to hover over anything.  format_html escapes
    # the event and requirement names.
    prerequisite_list = format_html_join(
        '',
        '<p class="mb-0 {}"><strong>{}</strong></p><ul class="mb-0">{}</ul>',
        (
            (
                'mt-2' if index else '',
                event_name,
                format_html_join('', '<li>{}</li>', ((n,) for n in req_names)),
            )
            for index, (event_name, req_names) in enumerate(events.values())
        ),
    )
    help_text = format_html(
        '<div class="alert alert-primary mt-2 mb-0" role="note">{}</div>',
        prerequisite_list,
    )

    field_name = 'acknowledge_prerequisites'
    field = django_forms.BooleanField(
        required=True,
        label=_('I confirm that I meet the prerequisites for the classes I have registered for'),
        help_text=help_text,
    )
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
