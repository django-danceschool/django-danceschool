from django.template import Template, Context
from django.utils.translation import ugettext_lazy as _

import re
import six

from .tasks import sendEmail
from .models import EventRegistration, TemporaryEventRegistration

if six.PY3:
    # Ensures that checks for Unicode data types (and unicode type assignments) do not break.
    unicode = str


def renderEmail(subject,content,from_address,from_name='',cc=[],to=[],bcc=[],registrations=[],temporaryregistrations=[],eventregistrations=[],event=None,attachment_name=None,attachment=None,**kwargs):
    '''
    This function renders email templates (typically pulled from the database)
    and queues the appropriate emails for sending.  By default, email templates
    can have a handful of registration-specific context variables and event-specific
    context variables.  However, arbitrary context variables may be passed as keyword
    arguments as well.
    '''

    # Ensure that to, cc, and bcc are all in list format
    if type(to) in [str,unicode]:
        to = [to,]
    if to is None:
        to = []
    if type(cc) in [str,unicode]:
        cc = [cc,]
    if cc is None:
        cc = []
    if type(bcc) in [str,unicode]:
        bcc = [bcc,]
    if bcc is None:
        bcc = []

    # Either registrations, eventregistrations, or emails must be populated
    if not registrations and not bcc and not to and not cc and not eventregistrations:
        raise ValueError(_('Email must have a recipient.'))
    if registrations and eventregistrations:
        raise ValueError(_('Cannot pass both eventregistrations and registrations.'))
    if registrations and temporaryregistrations:
        raise ValueError(_('Cannot pass both temporaryregistrations and registrations.'))
    if eventregistrations and temporaryregistrations:
        raise ValueError(_('Cannot pass both temporaryregistrations and eventregistrations.'))

    if event:
        kwargs.update({
            'event_id': event.id,
            'event_name': event.__str__(),
            'event_title': event.name,
            'event_start': event.eventoccurrence_set.first().startTime.strftime("%A, %B %d, %I:%M%p")
        })

    # In situations where there are no registration-specific context
    # variables to be rendered, send a mass email
    has_tags = re.search('\{\{.+\}\}',content)
    if not has_tags or (not registrations and not eventregistrations and not temporaryregistrations):
        if registrations:
            bcc += [x.customer.email for x in registrations]
        if eventregistrations:
            bcc += [x.customer.email for x in eventregistrations]
        if temporaryregistrations:
            bcc += [x.email for x in temporaryregistrations]

        t = Template(content)
        rendered_content = t.render(Context(kwargs))
        sendEmail(subject,rendered_content,from_address,from_name,cc,to,bcc,attachment_name=attachment_name,attachment=attachment)
        return

    # Otherwise, we must make multiple calls to send an email, one per
    # registration or eventregistration
    for registration in registrations:
        registration_kwargs = {}

        eventregs = EventRegistration.objects.filter(registration=registration)

        eventList = ""
        for er in eventregs:
            title = er.event.name
            start = er.event.eventoccurrence_set.first().startTime.strftime("%A, %B %d, %I:%M%p")
            eventList += _('%s, begins on %s' % (title,start)) + "\n"

        registration_kwargs.update({
            'first_name': registration.firstName,
            'last_name': registration.lastName,
            'eventList': eventList,
            'registrationAmountPaid': registration.amountPaid,
            'registrationComments': registration.comments,
            'registrationHowHeardAboutUs': registration.howHeardAboutUs,
        })
        registration_kwargs.update(kwargs)
        registration_bcc = bcc + [registration.customer.email]

        # For security reasons, the following tags are removed from the template before parsing:
        # {% extends %}{% load %}{% debug %}{% include %}{% ssi %}
        content = re.sub('\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}','',content)

        t = Template(content)
        # TODO: Replace with more limited regular expression replacement
        # to limit ability to use full template engine features.

        rendered_content = t.render(Context(registration_kwargs))
        sendEmail(subject,rendered_content,from_address,from_name,cc,to,registration_bcc,attachment_name=attachment_name,attachment=attachment)

    # Otherwise, we must make multiple calls to send an email, one per
    # registration or eventregistration
    for registration in temporaryregistrations:
        registration_kwargs = {}

        eventregs = TemporaryEventRegistration.objects.filter(registration=registration)

        eventList = ""
        for er in eventregs:
            title = er.event.name
            start = er.event.eventoccurrence_set.first().startTime.strftime("%A, %B %d, %I:%M%p")
            eventList += _('%s, begins on %s' % (title,start)) + "\n"

        registration_kwargs.update({
            'first_name': registration.firstName,
            'last_name': registration.lastName,
            'eventList': eventList,
            'registrationAmountDue': registration.priceWithDiscount,
            'registrationDiscountAmount': registration.totalDiscount,
            'registrationComments': registration.comments,
            'registrationHowHeardAboutUs': registration.howHeardAboutUs,
        })
        registration_kwargs.update(kwargs)
        registration_bcc = bcc + [registration.email]

        # For security reasons, the following tags are removed from the template before parsing:
        # {% extends %}{% load %}{% debug %}{% include %}{% ssi %}
        content = re.sub('\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}','',content)

        t = Template(content)
        # TODO: Replace with more limited regular expression replacement
        # to limit ability to use full template engine features.

        rendered_content = t.render(Context(registration_kwargs))
        sendEmail(subject,rendered_content,from_address,from_name,cc,to,registration_bcc,attachment_name=attachment_name,attachment=attachment)

    # Otherwise, we must make multiple calls to send an email, one per
    # registration or eventregistration
    for er in eventregistrations:
        registration_kwargs = {}

        title = er.event.name
        start = er.event.eventoccurrence_set.first().startTime.strftime("%A, %B %d, %I:%M%p")
        eventList = _('%s, begins on %s' % (title,start)) + "\n"

        registration_kwargs.update({
            'first_name': er.registration.firstName,
            'last_name': er.registration.lastName,
            'eventList': eventList,
        })
        registration_kwargs.update(kwargs)
        registration_bcc = bcc + [er.registration.customer.email]

        # For security reasons, the following tags are removed from the template before parsing:
        # {% extends %}{% load %}{% debug %}{% include %}{% ssi %}
        content = re.sub('\{%\s*((extends)|(load)|(debug)|(include)|(ssi))\s+.*?\s*%\}','',content)

        t = Template(content)
        # TODO: Replace with more limited regular expression replacement
        # to limit ability to use full template engine features.

        rendered_content = t.render(Context(registration_kwargs))
        sendEmail(subject,rendered_content,from_address,from_name,cc,to,registration_bcc,attachment_name=attachment_name,attachment=attachment)
