from django.http import HttpResponseRedirect, Http404, HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder
from django.views.generic import (
    FormView, CreateView, UpdateView, DetailView, TemplateView, ListView,
    RedirectView
)
from django.db.models import Min, Q, Count, F, Case, When, BooleanField
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.mixins import AccessMixin
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from calendar import month_name
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from itertools import chain
from urllib.parse import unquote_plus, unquote
from braces.views import UserFormKwargsMixin, PermissionRequiredMixin, LoginRequiredMixin, StaffuserRequiredMixin
from cms.constants import RIGHT
from cms.models import Page
import re
import logging
import json

from .models import (
    ClassDescription, Event, Series, PublicEvent, EventOccurrence, EventRole, EventRegistration,
    StaffMember, Instructor, Invoice, Customer, EventCheckIn
)
from .forms import (
    SubstituteReportingForm, StaffMemberBioChangeForm, RefundForm, EmailContactForm,
    RepeatEventForm, InvoiceNotificationForm, EventAutocompleteForm
)
from .constants import getConstant, EMAIL_VALIDATION_STR, REFUND_VALIDATION_STR
from .mixins import (
    EmailRecipientMixin, StaffMemberObjectMixin, FinancialContextMixin,
    AdminSuccessURLMixin, EventOrderMixin, SiteHistoryMixin,
    ReferralInfoMixin
)
from .signals import get_customer_data, get_eventregistration_data
from .utils.requests import getIntFromGet
from .utils.timezone import ensure_timezone, ensure_localtime


# Define logger for this file
logger = logging.getLogger(__name__)


class EventRegistrationSelectView(PermissionRequiredMixin, EventOrderMixin, FormView):
    '''
    This view is used to select an event for viewing registration data in
    the EventRegistrationSummaryView
    '''
    template_name = 'core/events_viewregistration_list.html'
    permission_required = 'core.view_registration_summary'
    reverse_time_ordering = True
    form_class = EventAutocompleteForm

    def get_queryset(self):
        ''' Recent events are listed in link form. '''

        return Event.objects.filter(
            Q(startTime__gte=timezone.now() - timedelta(days=90)) & (
                Q(series__isnull=False) | Q(publicevent__isnull=False)
            )
        ).annotate(count=Count('eventregistration')).annotate(**self.get_annotations()).exclude(
            Q(count=0) & Q(status__in=[
                Event.RegStatus.hidden, Event.RegStatus.regHidden, Event.RegStatus.disabled
            ])
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        context.update({'queryset': queryset, 'object_list': queryset, 'event_list': queryset})
        return context

    def form_valid(self, form):
        return HttpResponseRedirect(reverse(
            'viewregistrations',
            args=(form.cleaned_data.get('event').id,)
        ))


class EventRegistrationSummaryView(PermissionRequiredMixin, SiteHistoryMixin, DetailView):
    '''
    This view is used to access the set of registrations for a given series or event
    '''
    template_name = 'core/view_eventregistrations.html'
    permission_required = 'core.view_registration_summary'

    def get_object(self, queryset=None):
        return get_object_or_404(
            Event.objects.filter(id=self.kwargs.get('event_id')))

    def get_context_data(self, **kwargs):
        ''' Add the list of registrations for the given series '''

        # Update the site session data so that registration processes know to send return links to
        # the view class registrations page.  set_return_page() is in SiteHistoryMixin.
        self.set_return_page('viewregistrations', _('View Registrations'), event_id=self.object.id)

        registrations = EventRegistration.objects.filter(
            event=self.object, cancelled=False,
            registration__final=True,
        ).select_related(
            'registration', 'event', 'customer',
            'invoiceItem', 'role', 'registration__invoice',
        ).order_by(
            F('registration__lastName').asc(nulls_last=True),
            F('registration__firstName').asc(nulls_last=True),
        )

        extras_dict = {x: [] for x in registrations.values_list('id', flat=True)}

        if registrations:
            extras = get_eventregistration_data.send(
                sender=EventRegistrationSummaryView, eventregistrations=registrations
            )
            for k, v in chain.from_iterable([x.items() for x in [y[1] for y in extras if y[1]]]):
                extras_dict[k].extend(v)

        context = {
            'event': self.object,
            'registrations': registrations,
            'extras': extras_dict,
        }
        context.update(kwargs)
        return super().get_context_data(**context)


class EventRegistrationJsonView(PermissionRequiredMixin, ListView):
    '''
    This view is used to access a list of event registrations for a particular date.
    '''
    permission_required = 'core.view_registration_summary'

    def post(self, request, *args, **kwargs):
        ''' Parse the date and customer information that is passed. '''

        def recurse_listing(listing, obj, extras=None, startTime=None, checkInType='O'):
            '''
            Recursively go through a list of model attributes, including attributes that
            are of linked models.
            '''

            this_dict = {}
            if not isinstance(listing, list):
                raise ValueError('Invalid listing for recursion.')

            for item in listing:
                if isinstance(item, str):
                    # Handle a couple of special cases
                    if item == 'checkedIn':
                        kwargs = {'checkInType': checkInType}
                        if isinstance(startTime, datetime):
                            kwargs['date'] = startTime.date()
                        this_dict[item] = getattr(obj, item, None)(**kwargs)
                    elif item == 'getNextOccurrenceForDate':
                        # This view always uses the beginning of the current day
                        # when searching for the next EventOccurrence, to avoid
                        # unexpected behavior when using it for at-the-door
                        # registration.
                        this_dict[item] = getattr(
                            getattr(obj, item, None)(startTime),
                            'id', None
                        )
                    else:
                        this_dict[item] = getattr(obj, item, None)

                elif isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
                    this_item = getattr(obj, item[0], None)

                    # Added because of issues with polymorphic queries; we need
                    # to ensure we have the child model.
                    if item[0] == 'event':
                        this_item = getattr(
                            this_item, this_item.polymorphic_ctype.model, None
                        )

                    this_dict[item[0]] = recurse_listing(
                        item[1], this_item, startTime=startTime,
                        checkInType=checkInType
                    )

            if (
                isinstance(obj, EventRegistration) and
                extras_dict is not None and
                extras_dict.get(obj.id, None)
            ):
                this_dict['extras'] = extras_dict[obj.id]

            return this_dict

        try:
            post_data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError:
            data = json.dumps(
                {'code': 'invalid_json', 'message': _('Invalid JSON.')},
                cls=DjangoJSONEncoder
            )
            return HttpResponse(data, content_type='application/json')

        if post_data.get('date', None):
            try:
                self.startTime = ensure_localtime(datetime.strptime(post_data.get('date', ''), '%Y-%m-%d'))
                self.endTime = self.startTime + timedelta(days=1)
            except ValueError:
                logger.warning('Invalid date passed to EventRegistrationJsonView.')

        if post_data.get('id', None):
            try:
                self.customer = Customer.objects.get(id=post_data.get('id'))
            except ObjectDoesNotExist:
                logger.warning('Invalid customer passed to EventRegistrationJsonView.')

        # Only set the attribute if passed, but the downstream uses of this
        # attribute default to occurrence-based check-in unless otherwise
        # specified. Ignore invalid choices.
        if (
            post_data.get('checkInType', None) in
            [x[0] for x in EventCheckIn.CHECKIN_TYPE_CHOICES]
        ):
            self.checkInType = post_data.get('checkInType')

        queryset = self.get_queryset()

        if post_data.get('eventList'):
            queryset = queryset.filter(event__id__in=post_data.get('eventList'))

        # These are all the various attributes that we want to be populated in the response JSON
        attributeList = [
            'id', 'dropIn', 'refundFlag', 'warningFlag',
            'checkedIn', 'occurrenceId', 'occurrenceStartTime',
            ('event', ['id', 'name', 'url',]),
            ('registration', [
                'id', 'student', 'refundFlag',
                'fullName', 'grossTotal', 'total', 'discounted', 'url',
                ('customer', ['id', 'fullName', 'email', 'numClassSeries']),
                ('invoice', ['id', 'grossTotal', 'total', 'adjustments', 'taxes', 'fees', 'outstandingBalance', 'statusLabel', 'url']),
            ]),
            ('invoiceItem', [
                'id', 'grossTotal', 'total', 'adjustments', 'taxes', 'fees', 'revenueMismatch', 'revenueNotYetReceived',
                'revenueReceived', 'revenueReported'
            ]),
            ('role', ['id', 'name']),
        ]

        extras_dict = {}

        if queryset:
            extras = get_eventregistration_data.send(sender=EventRegistrationJsonView, eventregistrations=queryset)
            extras_dict = {x: [] for x in queryset.values_list('id', flat=True)}
            for k, v in chain.from_iterable([x.items() for x in [y[1] for y in extras if isinstance(y[1], dict)]]):
                extras_dict[k].extend(v)

        this_listing = [
            recurse_listing(
                attributeList, q, extras=extras_dict,
                startTime=getattr(self, 'startTime', None),
                checkInType=getattr(self, 'checkInType', 'O')
            )
            for q in queryset
        ]

        data = json.dumps(this_listing, cls=DjangoJSONEncoder)
        return HttpResponse(data, content_type='application/json')

    def get_queryset(self):
        filters = {'cancelled': False}
        if getattr(self, 'startTime', None):
            filters['event__eventoccurrence__endTime__gte'] = self.startTime
        if getattr(self, 'endTime', None):
            filters['event__eventoccurrence__startTime__lte'] = self.endTime
        if getattr(self, 'customer', None):
            filters['registration__customer'] = self.customer

        dropInFilters = Q(dropIn=False) | (Q(dropIn=True) & Q(occurrences__id=F('occurrenceId')))

        registrations = EventRegistration.objects.filter(
            **filters
        ).annotate(
            occurrenceId=F('event__eventoccurrence__id'),
            occurrenceStartTime=F('event__eventoccurrence__startTime'),
        ).filter(dropInFilters).select_related(
            'registration', 'event', 'customer',
            'invoiceItem', 'role', 'registration__invoice',
        ).order_by('registration__firstName', 'registration__lastName')
        return registrations


#################################
# Used for various form submission redirects (called by the AdminSuccessURLMixin)


class SubmissionRedirectView(SiteHistoryMixin, TemplateView):
    template_name = 'cms/forms/submission_redirect.html'

    def get_context_data(self, **kwargs):
        '''
        The URL to redirect to can be explicitly specified, or it can come
        from the site session history, or it can be the default admin success page
        as specified in the site settings.
        '''

        context = super().get_context_data(**kwargs)

        redirect_url = unquote(self.request.GET.get('redirect_url', ''))
        if not redirect_url:
            redirect_url = self.get_return_page().get('url', '')
        if not redirect_url:
            try:
                redirect_url = Page.objects.get(
                    pk=getConstant('general__defaultAdminSuccessPage')
                ).get_absolute_url(settings.LANGUAGE_CODE)
            except ObjectDoesNotExist:
                redirect_url = '/'

        context.update({
            'redirect_url': redirect_url,
            'seconds': self.request.GET.get('seconds', 5),
        })

        return context

################################################
# For Viewing Invoices and sending notifications


class ViewInvoiceView(AccessMixin, FinancialContextMixin, SiteHistoryMixin, DetailView):
    template_name = 'core/invoice.html'
    model = Invoice

    def get(self, request, *args, **kwargs):
        '''
        Invoices can be viewed only if the validation string is provided, unless
        the user is logged in and has view_all_invoice permissions
        '''
        self.object = self.get_object()
        user_has_permissions = request.user.has_perm('core.view_all_invoices')
        user_has_validation_string = (
            request.GET.get('v', None) == self.object.validationString
        )

        if user_has_validation_string or user_has_permissions:
            context = self.get_context_data(
                object=self.object,
                user_has_permissions=user_has_permissions,
                user_has_validation_string=user_has_validation_string
            )
            return self.render_to_response(context)
        return self.handle_no_permission()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'invoice': self.object,
            'payments': self.get_payments(),
        })

        # Update the session data so that subsequent views return to this page.
        self.set_return_page('viewInvoice', _('Invoice'), pk=str(self.object.pk))

        return context

    def get_payments(self):
        if not getattr(self, 'payments', None):
            self.payments = self.object.get_payments()
        return self.payments


class InvoiceNotificationView(FinancialContextMixin, AdminSuccessURLMixin,
                              PermissionRequiredMixin, StaffuserRequiredMixin, FormView):
    success_message = _('Invoice notifications successfully sent.')
    template_name = 'core/invoice_notification.html'
    permission_required = 'core.send_invoices'
    form_class = InvoiceNotificationForm

    def form_valid(self, form):
        invoice_ids = [
            k.replace('invoice_', '') for k, v in form.cleaned_data.items() if 'invoice_' in k and v is True
        ]
        invoices = [x for x in self.toNotify if str(x.id) in invoice_ids]

        for invoice in invoices:
            if invoice.get_default_recipients():
                invoice.sendNotification()

        messages.success(self.request, self.success_message)
        return HttpResponseRedirect(self.get_success_url())

    def dispatch(self, request, *args, **kwargs):
        ''' Get the set of invoices for which to permit notifications '''

        if 'pk' in self.kwargs:
            try:
                self.invoices = Invoice.objects.filter(pk=self.kwargs.get('pk'))[:]
            except ValueError:
                raise Http404()
            if not self.invoices:
                raise Http404()
        else:
            ids = request.GET.get('invoices', '')
            try:
                self.invoices = Invoice.objects.filter(id__in=[x for x in ids.split(', ')])[:]
            except ValueError:
                return HttpResponseBadRequest(_('Invalid invoice identifiers specified.'))

        if not self.invoices:
            return HttpResponseBadRequest(_('No invoice identifiers specified.'))

        toNotify = []
        cannotNotify = []

        for invoice in self.invoices:
            if invoice.get_default_recipients():
                toNotify.append(invoice)
            else:
                cannotNotify.append(invoice)
        self.toNotify = toNotify
        self.cannotNotify = cannotNotify

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        ''' Pass the set of invoices to the form for creation '''
        kwargs = super().get_form_kwargs()
        kwargs['invoices'] = self.toNotify
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'toNotify': self.toNotify,
            'cannotNotify': self.cannotNotify,
        })
        return context


#################################
# Refund processing and confirmation step views


class RefundConfirmationView(FinancialContextMixin, AdminSuccessURLMixin, PermissionRequiredMixin,
                             StaffuserRequiredMixin, SuccessMessageMixin, TemplateView):
    success_message = _('Refund successfully processed.')
    template_name = 'core/refund_confirmation.html'
    permission_required = 'core.process_refunds'

    def get(self, request, *args, **kwargs):
        self.form_data = request.session.get(REFUND_VALIDATION_STR, {}).get('form_data', {})
        if not self.form_data:
            return HttpResponseRedirect(reverse('refundProcessing', args=(self.form_data.get('id'),)))

        try:
            self.invoice = Invoice.objects.get(id=self.form_data.get('id'))
        except ObjectDoesNotExist:
            return HttpResponseRedirect(reverse('refundProcessing', args=(self.form_data.get('id'),)))

        self.payments = self.invoice.get_payments()

        if request.GET.get('confirmed', '').lower() == 'true' and self.payments:
            return self.process_refund()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        total_refund_amount = self.form_data['total_refund_amount']
        initial_refund_amount = self.form_data['initial_refund_amount']
        amount_to_refund = max(total_refund_amount - initial_refund_amount, 0)

        context.update({
            'form_data': self.form_data,
            'payments': self.payments,
            'total_refund_amount': total_refund_amount,
            'initial_refund_amount': initial_refund_amount,
            'amount_to_refund': amount_to_refund,
        })
        return context

    def process_refund(self):

        refund_data = self.invoice.data.get('refunds', [])

        total_refund_amount = self.form_data['total_refund_amount']
        initial_refund_amount = self.form_data['initial_refund_amount']
        amount_to_refund = max(total_refund_amount - initial_refund_amount, 0)

        # Identify the items to which refunds should be allocated and update the adjustments line
        # for those items.  Fees are also allocated across the items for which the refund was requested.
        refund_items = self.form_data.items()
        item_refund_data = [(k.split('_')[2], v) for k, v in refund_items if k.startswith('item_refundamount_')]
        adjustment_amounts = {x[0]: float(x[1]) for x in item_refund_data}

        # Keep track of total refund fees as well as how much reamins to be
        # refunded as we iterate through payments to refund them.
        remains_to_refund = amount_to_refund

        for this_payment in self.payments:
            if remains_to_refund <= 0:
                break
            if not this_payment.refundable:
                continue

            this_payment_amount = this_payment.netAmountPaid or 0
            this_refund_amount = min(this_payment_amount, remains_to_refund)

            # This dictionary will be updated and then added to refund_data for
            # this invoice whether the refund is successful or not
            this_refund_response_data = {
                'datetime': str(ensure_localtime(timezone.now())),
                'id': this_payment.recordId,
                'methodName': this_payment.methodName,
                'amount': this_refund_amount,
            }

            this_refund_response = this_payment.refund(this_refund_amount)

            if not this_refund_response:
                # If no response is received, then we must stop because we cannot be sure that a refund has
                # not already been processed.
                this_refund_response_data.update({
                    'status': 'error',
                    'errorMessage': str(_('Error: No response from payment processing app. '
                                          'Check payment processor records for refund status.')),
                })
            elif this_refund_response[0].get('status').lower() == 'success':
                # A successful refund returns {'status': 'success'}
                amount_refunded = this_refund_response[0].get('refundAmount', 0)
                fees = this_refund_response[0].get('fees', 0)

                this_refund_response_data.update({
                    'status': 'success',
                    'refundAmount': amount_refunded,
                    'fees': fees,
                    'response': [dict(this_refund_response[0]), ],
                })

                remains_to_refund -= amount_refunded

            else:
                this_refund_response_data.update({
                    'status': 'error',
                    'errorMessage': _('An unkown error has occurred. '
                                      'Check payment processor records for refund status.'),
                    'response': [dict(this_refund_response[0]), ],
                    'id': this_payment.recordId,
                    'methodName': this_payment.methodName,
                    'invoice': self.invoice.id,
                    'refundAmount': this_refund_amount,
                })
            refund_data.append(this_refund_response_data)

            if this_refund_response_data.get('status') == 'error':
                logger.error(this_refund_response_data.get('errorMessage'))
                logger.error(this_refund_response_data)

                messages.error(self.request, this_refund_response_data.get('errorMessage'))

                self.invoice.data['refunds'] = refund_data

                total_applied = sum([x.get('refundAmount', 0) for x in refund_data if x.get('status') == 'success'])
                total_fees = sum([x.get('fees', 0) for x in refund_data if x.get('status') == 'success'])

                # Allocate whatever amount was previously successful across the
                # items for which the refund was requested.
                self.invoice.amountPaid -= total_applied

                self.invoice.updateTotals(
                    save=True,
                    allocateAmounts={
                        'adjustments': -1*total_applied,
                        'fees': total_fees,
                    },
                    allocateWeights=adjustment_amounts
                )
                self.request.session.pop(REFUND_VALIDATION_STR, None)
                return HttpResponseRedirect(self.get_success_url())

        # If there were no errors, then check to ensure that the entire request refund was refunded.
        # If so, then return success, otherwise return indicating that the refund was not completely
        # applied.
        if abs(remains_to_refund) <= 0.01:
            messages.success(self.request, self.success_message)
        else:
            messages.error(
                self.request,
                _('Error, not all of the requested refund was applied. '
                  'Check invoice and payment processor records for details.')
                )

        self.invoice.data['refunds'] = refund_data

        total_applied = sum([x.get('refundAmount', 0) for x in refund_data if x.get('status') == 'success'])
        total_fees = sum([x.get('fees', 0) for x in refund_data if x.get('status') == 'success'])

        self.invoice.amountPaid -= total_applied

        if abs(
            self.invoice.total + (self.invoice.taxes * self.invoice.buyerPaysSalesTax) +
            self.invoice.adjustments - total_applied
        ) < 0.01:
            self.invoice.status = Invoice.PaymentStatus.fullRefund

        # Allocate whatever amount was previously successful across the
        # items for which the refund was requested.
        items = self.invoice.updateTotals(
            save=True,
            allocateAmounts={
                'adjustments': -1*total_applied,
                'fees': total_fees,
            },
            allocateWeights=adjustment_amounts
        )

        # If the refund is a complete refund and is associated with a registration,
        # then cancel the EventRegistration entirely.
        eventregs = EventRegistration.objects.filter(invoiceItem__in=items)
        for this_item in items:
            this_eventreg = eventregs.filter(invoiceItem=this_item).first()

            if (
                abs(
                    this_item.total + this_item.adjustments +
                    (this_item.taxes * self.invoice.buyerPaysSalesTax)
                ) < 0.01 and this_eventreg
            ):
                this_eventreg.cancelled = True
                this_eventreg.save()

        self.request.session.pop(REFUND_VALIDATION_STR, None)
        return HttpResponseRedirect(self.get_success_url())


class RefundProcessingView(FinancialContextMixin, PermissionRequiredMixin, StaffuserRequiredMixin, UpdateView):
    template_name = 'core/process_refund.html'
    form_class = RefundForm
    permission_required = 'core.process_refunds'
    model = Invoice

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'invoice': self.object,
            'payments': self.get_payments(),
        })
        if getattr(self.object, 'registration', None):
            context['registration'] = self.object.registration

        return context

    def form_valid(self, form):
        # Avoid JSON serialization issues by passing the Invoice ID, not the object itself
        clean_data = form.cleaned_data
        clean_data['id'] = str(clean_data.get('id').id)

        self.request.session[REFUND_VALIDATION_STR] = {
            'form_data': clean_data,
            'invoice': str(self.object.id),
        }
        return HttpResponseRedirect(reverse('refundConfirmation'))

    def get_payments(self):
        if not getattr(self, 'payments', None):
            self.payments = self.object.get_payments()
        return self.payments


#################################
# Email view function and form


class EmailConfirmationView(AdminSuccessURLMixin, PermissionRequiredMixin, TemplateView):
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
        month = self.form_data.pop('month')
        series = self.form_data.pop('series')
        customers = self.form_data.pop('customers', [])

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
        if month is not None and month != '':
            get_month = datetime.strptime(month, '%m-%Y').month
            get_year = datetime.strptime(month, '%m-%Y').year
            items_to_send += list(Series.objects.filter(month=get_month, year=get_year))
        if series not in [None, '', [], ['']]:
            items_to_send += list(Event.objects.filter(id__in=series))
        if customers:
            items_to_send.append(list(Customer.objects.filter(id__in=customers)))

        # We always call one email per series so that the series-level tags
        # can be passed.  The entire list of customers is also a single item
        # in the items_to_send list, because they can be processed all at once.
        for s in items_to_send:
            if isinstance(s, Event):
                regs = EventRegistration.objects.filter(event=s, cancelled=False)
                emails = []
                for x in regs:
                    emails += x.get_default_recipients() or []
            else:
                # Customers are themselves the list.
                regs = s
                emails = [x.email for x in s]

            email_kwargs['cc'] = []
            if cc_myself:
                email_kwargs['cc'].append(email_kwargs['from_address'])

            email_kwargs['bcc'] = [email_kwargs['from_address'] or getConstant('email__defaultEmailFrom'), ]

            if testemail:
                message = str(_('Test email from %s to be sent to: ' % email_kwargs['from_address'])) + '\n\n'
                message += ', '.join(email_kwargs['bcc']) + ', '.join(emails) + '\n\n'
                message += str(_('Email body:')) + '\n\n' + message
                email_kwargs['bcc'] = []

            # If there are no context tags, then this can be sent as a single bulk email.
            # Otherwise, send a separate email for each event registration
            has_tags = re.search(r'\{\{.+\}\}', message)
            if not has_tags:
                email_kwargs['bcc'] += emails
                # Avoid duplicate emails
                email_kwargs['bcc'] = list(set(email_kwargs['bcc']))

                # instantiate the recipient mixin directly
                email_class = EmailRecipientMixin()
                email_class.email_recipient(subject, message, **email_kwargs)
            else:
                for r in regs:
                    r.email_recipient(subject, message, **email_kwargs)

        self.request.session.pop(EMAIL_VALIDATION_STR, None)
        messages.success(self.request, self.success_message)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.form_data)

        month = self.form_data['month']
        series = self.form_data['series']
        customers = self.form_data.get('customers')
        from_address = self.form_data['from_address']
        cc_myself = self.form_data['cc_myself']

        events_to_send = []
        if month is not None and month != '':
            get_month = datetime.strptime(month, '%m-%Y').month
            get_year = datetime.strptime(month, '%m-%Y').year
            events_to_send += Series.objects.filter(month=get_month, year=get_year)
        if series not in [None, '', [], ['']]:
            events_to_send += [Event.objects.get(id=x) for x in series]

        # We always call one email per series so that the series-level tags
        # can be passed.
        regs = EventRegistration.objects.filter(event__in=events_to_send)

        customerSet = Customer.objects.filter(id__in=customers) if customers else []

        emails = [r.customer.email for r in regs] + [r.email for r in customerSet]
        cc = []
        if cc_myself:
            cc.append(from_address)
        bcc = [getConstant('email__defaultEmailFrom')]

        context.update({
            'events_to_send': events_to_send,
            'customers_to_send': customerSet,
            'emails': emails,
            'cc': cc,
            'bcc': bcc,
        })

        return context


class SendEmailView(PermissionRequiredMixin, UserFormKwargsMixin, FormView):
    form_class = EmailContactForm
    permission_required = 'core.send_email'
    template_name = 'cms/forms/display_form_classbased_admin.html'

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
        Get the list of recent months and recent series to pass to the form
        '''

        numMonths = 12
        lastStart = (
            Event.objects.annotate(Min('eventoccurrence__startTime'))
            .order_by('-eventoccurrence__startTime__min')
            .values_list('eventoccurrence__startTime__min', flat=True)
            .first()
        )
        if lastStart:
            month = lastStart.month
            year = lastStart.year
        else:
            month = timezone.now().month
            year = timezone.now().year

        months = [('', _('None'))]
        for i in range(0, numMonths):
            newmonth = (month - i - 1) % 12 + 1
            newyear = year
            if month - i - 1 < 0:
                newyear = year - 1
            newdate = datetime(year=newyear, month=newmonth, day=1)
            newdateStr = newdate.strftime("%m-%Y")
            monthStr = newdate.strftime("%B, %Y")
            months.append((newdateStr, monthStr))

        cutoff = timezone.now() - timedelta(days=120)

        allEvents = Event.objects.filter(startTime__gte=cutoff).order_by('-startTime')
        recentSeries = [('', 'None')] + [(x.id, '%s %s: %s' % (month_name[x.month], x.year, x.name)) for x in allEvents]

        kwargs = super().get_form_kwargs(**kwargs)
        kwargs.update({
            "months": months,
            "recentseries": recentSeries,
            "customers": self.customers,
        })
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


############################################
# Customer and Instructor Stats Views


class AccountProfileView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'core/account_profile.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = {}
        user = self.get_object()

        context.update({
            'primary_email': user.emailaddress_set.filter(primary=True).first(),
            'verified_emails': user.emailaddress_set.filter(verified=True),
            'unverified_emails': user.emailaddress_set.filter(verified=False),
        })

        if hasattr(user, 'customer'):
            context.update({
                'customer': user.customer,
                'customer_verified': user.emailaddress_set.filter(email=user.customer.email, verified=True).exists(),
            })
            context['customer_eventregs'] = EventRegistration.objects.filter(registration__customer=user.customer)

        context['verified_eventregs'] = EventRegistration.objects.filter(
            registration__customer__email__in=[x.email for x in context['verified_emails']]
        ).exclude(
            id__in=[x.id for x in context.get('customer_eventregs', [])]
        )
        context['submitted_eventregs'] = EventRegistration.objects.filter(
            registration__invoice__submissionUser=self.request.user, registration__payAtDoor=False
        ).exclude(
            id__in=[x.id for x in context.get('customer_eventregs', [])]
        ).exclude(
            id__in=[x.id for x in context.get('verified_eventregs', [])]
        )

        if hasattr(user, 'staffmember'):
            upcoming_events = Event.objects.filter(
                endTime__gt=timezone.now(),
                eventstaffmember__staffMember=user.staffmember).distinct().order_by('-startTime')
            context.update({
                'staffmember': user.staffmember,
                'upcoming_events': upcoming_events,
            })

        # Get any extra context data passed by other apps.  These data require unique keys, so when writing
        # a handler for this signal, be sure to provide unique context keys.
        if hasattr(user, 'customer'):
            extra_customer_data = get_customer_data.send(
                sender=AccountProfileView,
                customer=user.customer,
            )
            for item in extra_customer_data:
                if len(item) > 1 and isinstance(item[1], dict):
                    # Ensure that 'customer' is not overwritten and add everything else
                    item[1].pop('customer', None)
                    context.update(item[1])

        return super().get_context_data(**context)


class OtherAccountProfileView(PermissionRequiredMixin, AccountProfileView):
    permission_required = 'core.view_other_user_profiles'

    def get_object(self, queryset=None):
        if 'user_id' in self.kwargs:
            return get_object_or_404(User.objects.filter(id=self.kwargs.get('user_id')))
        else:
            return self.request.user


class InstructorStatsView(StaffMemberObjectMixin, PermissionRequiredMixin, DetailView):
    model = StaffMember
    template_name = 'core/instructor_stats.html'
    permission_required = 'core.view_own_instructor_stats'

    def get_context_data(self, **kwargs):
        instructor = self.object
        context = {}

        context.update({
            'instructor': instructor,
            'prior_series': Event.objects.filter(
                startTime__lte=timezone.now(),
                eventstaffmember__staffMember=instructor).order_by('-startTime'),
            'upcoming_series': Event.objects.filter(
                startTime__gt=timezone.now(),
                eventstaffmember__staffMember=instructor).order_by('-startTime'),
        })

        if context['prior_series']:
            context.update({'first_series': context['prior_series'].last(), })
            context.update({
                'teaching_since': month_name[context['first_series'].month] + ' ' + str(context['first_series'].year),
                'student_count': sum([x.numRegistered for x in context['prior_series']]),
            })
        context.update({'series_count': len(context['prior_series']) + len(context['upcoming_series'])})

        # Note: This get the detailview's context, not all the mixins.  Supering itself led to an infinite loop.
        return super(DetailView, self).get_context_data(**context)


class OtherInstructorStatsView(InstructorStatsView):
    permission_required = 'core.view_other_instructor_stats'

    def get_object(self, queryset=None):
        if 'first_name' in self.kwargs and 'last_name' in self.kwargs:
            first_name = re.sub('^_$','', self.kwargs['first_name'])
            last_name = re.sub('^_$','', self.kwargs['last_name'])

            return get_object_or_404(
                StaffMember.objects.filter(
                    **{'firstName': unquote_plus(first_name).replace('_', ' '),
                        'lastName': unquote_plus(last_name).replace('_', ' ')})
                    )
        else:
            return None


#####################################
# Individual Class Series/Event Views


class IndividualClassReferralView(ReferralInfoMixin, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        if (
            self.kwargs.get('session_slug', None) and
            self.kwargs.get('year', None) and
            self.kwargs.get('month', None)
        ):
            return reverse('classViewSessionMonth', kwargs=kwargs)
        elif (
            self.kwargs.get('session_slug', None)
        ):
            return reverse('classViewSession', kwargs=kwargs)
        else:
            return reverse('classView', kwargs=kwargs)


class IndividualPublicEventReferralView(ReferralInfoMixin, RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        if (
            self.kwargs.get('session_slug', None) and
            self.kwargs.get('year', None) and
            self.kwargs.get('month', None)
        ):
            return reverse('eventViewSessionMonth', kwargs=kwargs)
        elif (
            self.kwargs.get('session_slug', None)
        ):
            return reverse('eventViewSession', kwargs=kwargs)
        else:
            return reverse('eventView', kwargs=kwargs)


class IndividualEventView(ReferralInfoMixin, FinancialContextMixin, TemplateView):
    model_class = Event
    template_name = 'core/event_pages/individual_event.html'

    def dispatch(self, request, *args, **kwargs):
        # These are passed via the URL
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        session_slug = self.kwargs.get('session_slug')
        slug = self.kwargs.get('slug', '')

        if month:
            try:
                month_number = list(month_name).index(month or 0)
            except ValueError:
                raise Http404(_('Invalid month.'))

        model_class = getattr(self, 'model_class', Event)

        filters = ~Q(status=Event.RegStatus.hidden) \
            & ~Q(status=Event.RegStatus.linkOnly)
        if model_class == Series:
            filters = filters & Q(classDescription__slug=slug)
        elif model_class == PublicEvent:
            filters = filters & Q(slug=slug)

        if year and month:
            filters = filters & Q(year=year or None) & Q(month=month_number or None)
        if session_slug:
            filters = filters & Q(session__slug=session_slug)

        passedCase = Q(endTime__lt=timezone.now())
        if getConstant('registration__displayLimitDays') or 0 > 0:
            passedCase = passedCase | Q(
                startTime__gte=timezone.now() + timedelta(
                    days=getConstant('registration__displayLimitDays')
                )
            )

        self.event_set = model_class.objects.filter(
            filters
        ).annotate(
            registrationPassed=Case(
                When(passedCase, then=True), default=False,
                output_field=BooleanField()
            )
        )

        if not self.event_set:
            raise Http404(_('No events found.'))

        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        templates = [x.template for x in self.event_set if getattr(x, 'template', None)]
        if templates:
            return [templates[0],]
        else:
            return super().get_template_names()

    def get(self, request, *args, **kwargs):

        # This will pass through to the context data by default
        kwargs.update({'event_set': self.event_set})

        model_lower = getattr(self, 'model_class', Event).__name__.lower()
        app_name = getattr(self, 'app_name', 'core')

        # For each Event in the set, add a button to the toolbar to edit the Event details
        if (
            hasattr(request, 'user') and
            request.user.has_perm('%s.change_%s' % (app_name, model_lower))
        ):
            for this_event in self.event_set:
                this_title = _('Edit Event Details')
                if len(self.event_set) > 1:
                    this_title += ' (#%s)' % this_event.id
                change_link = reverse(
                    'admin:%s_%s_change' % (app_name, model_lower),
                    args=([this_event.id, ])
                )
                request.toolbar.add_button(this_title, change_link, side=RIGHT)

        return super().get(request, *args, **kwargs)


class IndividualClassView(IndividualEventView):
    model_class = Series
    template_name = 'core/event_pages/individual_class.html'


class IndividualPublicEventView(IndividualEventView):
    model_class = PublicEvent
    template_name = 'core/event_pages/individual_event.html'

    def get(self, request, *args, **kwargs):
        # If an alternative link is given by one or more of these events, then redirect to that.
        overrideLinks = [x.link for x in self.event_set if getattr(x, 'link', None)]
        if overrideLinks:
            return HttpResponseRedirect(overrideLinks[0])

        return super().get(request, *args, **kwargs)


#####################################
# View for Repeating Events from admin
class RepeatEventsView(SuccessMessageMixin, AdminSuccessURLMixin, PermissionRequiredMixin, FormView):
    '''
    This view is for an admin action to repeat events.
    '''
    template_name = 'core/repeat_events.html'
    form_class = RepeatEventForm
    permission_required = 'core.add_event'
    success_message = _('Repeated events created successfully.')

    def dispatch(self, request, *args, **kwargs):
        ids = request.GET.get('ids')
        ct = getIntFromGet(request, 'ct')

        try:
            contentType = ContentType.objects.get(id=ct)
            self.objectClass = contentType.model_class()
        except (ValueError, ObjectDoesNotExist):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        # This view only deals with subclasses of Events (Public Events, Series, etc.)
        if not isinstance(self.objectClass(), Event):
            return HttpResponseBadRequest(_('Invalid content type passed.'))

        try:
            self.queryset = self.objectClass.objects.filter(id__in=[int(x) for x in ids.split(', ')])
        except ValueError:
            return HttpResponseBadRequest(_('Invalid ids passed'))

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'events': self.queryset,
        })

        return context

    def form_valid(self, form):
        ''' For each object in the queryset, create the duplicated objects '''

        startDate = form.cleaned_data.get('startDate')
        repeatEvery = form.cleaned_data.get('repeatEvery')
        periodicity = form.cleaned_data.get('periodicity')
        quantity = form.cleaned_data.get('quantity')
        endDate = form.cleaned_data.get('endDate')

        # Create a list of start dates, based on the passed  values of repeatEvery,
        # periodicity, quantity and endDate.  This list will be iterated through to
        # create the new instances for each event.
        if periodicity == 'D':
            delta = {'days': repeatEvery}
        elif periodicity == 'W':
            delta = {'weeks': repeatEvery}
        elif periodicity == 'M':
            delta = {'months': repeatEvery}

        repeat_list = []
        this_date = startDate

        if quantity:
            for k in range(0, quantity):
                repeat_list.append(this_date)
                this_date = this_date + relativedelta(**delta)
        elif endDate:
            while (this_date <= endDate):
                repeat_list.append(this_date)
                this_date = this_date + relativedelta(**delta)

        # Now, loop through the events in the queryset to create duplicates of them
        for event in self.queryset:

            # For each new occurrence, we determine the new startime by the distance from
            # midnight of the first occurrence date, where the first occurrence date is
            # replaced by the date given in repeat list
            old_min_time = event.localStartTime.replace(hour=0, minute=0, second=0, microsecond=0)

            old_occurrence_data = [
                (x.startTime - old_min_time, x.endTime - old_min_time, x.cancelled)
                for x in event.eventoccurrence_set.all()
            ]

            old_role_data = [(x.role, x.capacity) for x in event.eventrole_set.all()]

            for instance_date in repeat_list:

                # Ensure that time zones are treated properly
                combined_datetime = datetime.combine(instance_date, datetime.min.time())
                new_datetime = ensure_timezone(combined_datetime, old_min_time.tzinfo)

                # Removing the pk and ID allow new instances of the event to
                # be created upon saving with automatically generated ids.
                event.id = None
                event.pk = None
                event.save()

                # Create new occurrences
                for occurrence in old_occurrence_data:
                    EventOccurrence.objects.create(
                        event=event,
                        startTime=new_datetime + occurrence[0],
                        endTime=new_datetime + occurrence[1],
                        cancelled=occurrence[2],
                    )

                # Create new event-specific role data
                for role in old_role_data:
                    EventRole.objects.create(
                        event=event,
                        role=role[0],
                        capacity=role[1],
                    )

                # Need to save twice to ensure that startTime etc. get
                # updated properly.
                event.save()

            return super().form_valid(form)


############################################################
# View for instructors to report that they substitute taught
#

class SubstituteReportingView(AdminSuccessURLMixin, PermissionRequiredMixin, UserFormKwargsMixin,
                              SuccessMessageMixin, CreateView):
    '''
    This view is used to report substitute teaching.
    '''
    template_name = 'cms/forms/display_form_classbased_admin.html'
    form_class = SubstituteReportingForm
    permission_required = 'core.report_substitute_teaching'
    success_message = _('Substitute teaching reported successfully.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Report Substitute Teaching'),
            'form_description': _('Use this form to report substitute teaching.'),
        })
        return context


############################################################
# View for instructors to change their bio information
#


class StaffMemberBioChangeView(AdminSuccessURLMixin, StaffMemberObjectMixin, PermissionRequiredMixin,
                               SuccessMessageMixin, UpdateView):
    '''
    This view now permits changing the instructor's bio information.
    '''
    model = StaffMember
    template_name = 'cms/forms/display_form_classbased_admin.html'
    form_class = StaffMemberBioChangeForm
    permission_required = 'core.update_instructor_bio'
    success_message = _('Staff member information updated successfully.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'form_title': _('Update Contact Information'),
            'form_description': _('Use this form to update your contact information.'),
        })
        return context


############################################################
# View for Instructor/Staff directory
#


class StaffDirectoryView(PermissionRequiredMixin, ListView):
    '''
    This view shows a directory of instructors/staff
    '''
    template_name = 'core/staff_directory.html'
    permission_required = 'core.view_staff_directory'
    queryset = StaffMember.objects.exclude(instructor__status__in=[
        Instructor.InstructorStatus.retired,
        Instructor.InstructorStatus.retiredGuest,
        Instructor.InstructorStatus.hidden,
    ])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        staff = context.get('staffmember_list', StaffMember.objects.none())

        context.update({
            'active_instructors_list': staff.filter(instructor__status='R'),
            'assistant_instructors_list': staff.filter(instructor__status__in=['T', 'A']),
            'guest_instructors_list': staff.filter(instructor__status='G'),
            'other_staff_list': staff.filter(instructor__isnull=True),
        })
        return context
