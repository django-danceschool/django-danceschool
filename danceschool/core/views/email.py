from django.http import HttpResponseRedirect, HttpResponseBadRequest, HttpResponse, JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.views.generic import FormView
from django.db.models import Q
from django.db.models.query import QuerySet
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from braces.views import PermissionRequiredMixin, UserFormKwargsMixin
import re

from ..models import Event, Customer, EventRegistration, EventStaffMember, EmailTemplate
from ..forms.email import EmailContactForm
from ..constants import getConstant, EMAIL_VALIDATION_STR
from ..mixins import AdminSuccessURLMixin, EmailRecipientMixin

import logging

logger = logging.getLogger(__name__)


#################################
# Email view function and form


class EmailConfirmationView(AdminSuccessURLMixin, PermissionRequiredMixin, FormView):
    permission_required = 'core.send_email'
    template_name = 'core/email_confirmation_page.html'
    success_message = _('Email sent successfully.')

    def get(self, request, *args, **kwargs):
        self.form_data = request.session.get(EMAIL_VALIDATION_STR, {}).get('form_data', {})
        if not self.form_data:
            return HttpResponseRedirect(reverse('emailStudents'))
        if request.GET.get('confirmed', '').lower() == 'true':
            return self.send_email()
        return super().get(request, *args, **kwargs)

    def send_email(self):
        subject = self.form_data.pop('subject')
        message = self.form_data.pop('message')
        html_message = self.form_data.pop('html_message', None)
        richTextChoice = self.form_data.pop('richTextChoice')
        cc_myself = self.form_data.pop('cc_myself')
        testemail = self.form_data.pop('testemail')
        events = self.form_data.pop('events')
        include_staff = self.form_data.pop('include_staff')
        customers = self.form_data.pop('customers', [])
        additional_cc = self.form_data.pop('additional_cc', [])
        additional_bcc = self.form_data.pop('additional_bcc', [])

        email_kwargs = {
            'from_name': self.form_data['from_name'],
            'from_address': self.form_data['from_address'],
        }

        if richTextChoice == 'HTML':
            email_kwargs.update({
                'send_html': True,
                'html_message': html_message,
            })

        items_to_send = []
        if isinstance(events, QuerySet):
            items_to_send += list(events)
        elif events not in [None, '', [], ['']]:
            items_to_send += list(Event.objects.filter(id__in=events))
        if customers:
            items_to_send.append(Customer.objects.filter(id__in=customers))

        # Ensure that an email can be sent to the additional CC and BCC
        # recipients even if no Event or customer has been specified
        if (not items_to_send) and (
            testemail or additional_cc or additional_bcc or cc_myself
        ):
            items_to_send.append([])

        if not items_to_send:
            self.request.session.pop(EMAIL_VALIDATION_STR, None)
            messages.warning(
                self.request,
                _('No recipients specified; email will not be sent.')
            )
            return HttpResponseRedirect(self.get_success_url())

        # We always call one email per event so that the event-level tags
        # can be passed.  The entire list of customers is also a single item
        # in the items_to_send list, because they can be processed all at once.
        for s in items_to_send:
            if isinstance(s, Event):
                regs = EventRegistration.objects.filter(event=s, cancelled=False)
                staff = EventStaffMember.objects.filter(event=s)
                emails = []
                for x in regs:
                    emails += x.get_default_recipients() or []
                if include_staff:
                    for x in staff:
                        emails += x.get_default_recipients() or []
            elif isinstance(s, QuerySet) and s.model is Customer:
                # Customers are themselves the list.
                regs = s
                emails = [x.email for x in s]
            elif isinstance(s, list):
                # A list of email addresses can also be accepted
                regs = []
                emails = s

            email_kwargs['cc'] = additional_cc
            if cc_myself:
                email_kwargs['cc'].append(email_kwargs['from_address'])

            email_kwargs['bcc'] = (
                additional_bcc +
                [email_kwargs['from_address'] or getConstant('email__defaultEmailFrom'), ]
            )

            if testemail:
                message = str(_('Test email from %s to be sent to: ' % email_kwargs['from_address'])) + '\n\n'
                message += ', '.join(email_kwargs['bcc']) + ', '.join(emails) + '\n\n'
                message += str(_('Email body:')) + '\n\n' + message
                email_kwargs['bcc'] = []
                email_kwargs['cc'] = [email_kwargs['from_address'],]
                emails = []

            # If there are no context tags, then this can be sent as a single bulk email.
            # Otherwise, send a separate email for each event registration
            has_tags = re.search(r'\{\{.+\}\}', message)
            if (not has_tags) or testemail:
                email_kwargs['bcc'] += emails
                # Avoid duplicate emails
                email_kwargs['bcc'] = list(set(email_kwargs['bcc']))

                # instantiate the recipient mixin directly
                email_class = EmailRecipientMixin()
                email_class.email_recipient(subject, message, **email_kwargs)
            else:
                for r in regs:
                    r.email_recipient(subject, message, **email_kwargs)
                if include_staff:
                    for r in staff:
                        r.email_recipient(subject, message, **email_kwargs)

        self.request.session.pop(EMAIL_VALIDATION_STR, None)
        messages.success(self.request, self.success_message)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.form_data)

        events = self.form_data['events']
        customers = self.form_data.get('customers')
        from_address = self.form_data['from_address']
        cc_myself = self.form_data['cc_myself']
        include_staff = self.form_data['include_staff']
        additional_cc = self.form_data.get('additional_cc', [])
        additional_bcc = self.form_data.get('additional_bcc', [])

        events_to_send = []
        if isinstance(events, QuerySet):
            events_to_send += list(events)
        elif events not in [None, '', [], ['']]:
            events_to_send += list(Event.objects.filter(id__in=events))

        # We always call one email per event so that the event-level tags
        # can be passed.
        regs = EventRegistration.objects.select_related('customer').filter(
            event__in=events_to_send
        )
        customerSet = Customer.objects.filter(id__in=customers) if customers else []

        staff = EventStaffMember.objects.none()
        if include_staff:
            staff = EventStaffMember.objects.select_related('staffMember').filter(
                event__in=events_to_send
            )

        emails = (
            [r.customer.email for r in regs if r.customer] +
            [r.staffMember.privateEmail for r in staff if r.staffMember.privateEmail] +
            [r.email for r in customerSet]
        )
        cc = additional_cc
        if cc_myself:
            cc.append(from_address)
        bcc = additional_bcc + [getConstant('email__defaultEmailFrom')]

        context.update({
            'events_to_send': events_to_send,
            'customers_to_send': customerSet,
            'emails': list(set(emails)),
            'cc': cc,
            'bcc': bcc,
        })

        return context


class SendEmailView(PermissionRequiredMixin, UserFormKwargsMixin, FormView):
    form_class = EmailContactForm
    permission_required = 'core.send_email'
    template_name = 'cms/forms/display_crispy_form_classbased_admin.html'

    def dispatch(self, request, *args, **kwargs):
        ''' If a list of customers or groups was passed, then parse it '''
        ids = request.GET.get('customers')
        groups = request.GET.get('customergroup')
        self.customers = None

        if ids or groups:
            # Initial filter applies to no one but allows appending by logical or
            filters = Q(id__isnull=True)

            if ids:
                filters = filters | Q(id__in=[int(x) for x in ids.split(', ')])
            if groups:
                filters = filters | Q(groups__id__in=[int(x) for x in groups.split(', ')])

            try:
                self.customers = Customer.objects.filter(filters)
            except ValueError:
                return HttpResponseBadRequest(_('Invalid customer ids passed'))

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self, **kwargs):
        '''
        Pass the list of customers to the form if applicable.
        '''

        kwargs = super().get_form_kwargs(**kwargs)
        kwargs['customers'] = self.customers
        return kwargs

    def get_initial(self):
        '''
        If the user already submitted the form and decided to return from the
        confirmation page, then re-populate the form
        '''
        initial = super().get_initial()

        form_data = self.request.session.get(EMAIL_VALIDATION_STR, {}).get('form_data', {})
        if form_data:
            initial.update(form_data)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Email Students'),
            'form_description': _('Use this form to contact current or recent students.'),
        })
        return context

    def form_valid(self, form):
        ''' Pass form data to the confirmation view '''
        form.cleaned_data.pop('template', None)
        self.request.session[EMAIL_VALIDATION_STR] = {'form_data': form.cleaned_data}
        return HttpResponseRedirect(reverse('emailConfirmation'))


def getEmailTemplate(request):
    '''
    This function handles the Ajax call made when a user wants a specific email template
    '''
    if request.method != 'POST':
        return HttpResponse(_('Error, no POST data.'))

    if not hasattr(request, 'user'):
        return HttpResponse(_('Error, not authenticated.'))

    template_id = request.POST.get('template')

    if not template_id:
        return HttpResponse(_("Error, no template ID provided."))

    try:
        this_template = EmailTemplate.objects.get(id=template_id)
    except ObjectDoesNotExist:
        return HttpResponse(_("Error getting template."))

    if this_template.groupRequired and this_template.groupRequired not in request.user.groups.all():
        return HttpResponse(_("Error, no permission to access this template."))
    if this_template.hideFromForm:
        return HttpResponse(_("Error, no permission to access this template."))

    return JsonResponse({
        'subject': this_template.subject,
        'content': this_template.content,
        'html_content': this_template.html_content,
        'richTextChoice': this_template.richTextChoice,
    })
