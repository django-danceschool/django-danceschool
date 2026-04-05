from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.views.generic import FormView, DetailView, ListView
from django.db.models import Q, F, Sum, FloatField, Count
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import datetime, timedelta
from itertools import chain
from braces.views import PermissionRequiredMixin
import json

from ..models import (
    Event, EventRegistration, InvoiceItem, Customer, EventCheckIn
)
from ..forms.event import EventAutocompleteForm
from ..constants import getConstant
from ..mixins import EventOrderMixin, SiteHistoryMixin
from ..signals import get_eventregistration_data, get_additional_event_names, get_person_data
from ..registries import extras_templates_registry
from ..utils.timezone import ensure_localtime

import logging

logger = logging.getLogger(__name__)


class EventRegistrationSelectView(PermissionRequiredMixin, EventOrderMixin, FormView):
    '''
    This view is used to select an event for viewing registration data in
    the EventRegistrationSummaryView.
    '''
    template_name = 'core/events_viewregistration_list.html'
    permission_required = 'core.view_registration_summary'
    reverse_time_ordering = False
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
        ).order_by(*self.get_ordering())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        context.update({
            'queryset': queryset, 'object_list': queryset,
            'event_list': queryset,
            'prior_events': queryset.filter(
                startTime__lt=ensure_localtime(timezone.now()).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            ),
            'upcoming_events': queryset.filter(
                startTime__gte=ensure_localtime(timezone.now()).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            ),
        })
        return context

    def form_valid(self, form):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
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

        registrations = list(EventRegistration.objects.filter(
            event=self.object, cancelled=False,
            registration__final=True,
        ).select_related(
            'registration', 'event', 'customer',
            'invoiceItem', 'invoiceItem__revenueitem', 'role',
            'registration__invoice',
        ).prefetch_related(
            'occurrences',
            'registration__registrationdiscount_set',
            'registration__registrationdiscount_set__discount',
            'registration__invoice__voucheruse_set',
            'registration__invoice__voucheruse_set__voucher',
        ).order_by(
            F('customer__last_name').asc(nulls_last=True),
            F('customer__first_name').asc(nulls_last=True),
        ))

        # Get all invoice IDs for these registrations
        invoice_ids = [
            reg.registration.invoice_id for reg in registrations
            if reg.registration.invoice_id
        ]

        # Single query: aggregate all invoice items across all invoices at once,
        # splitting by whether the item belongs to this registration's
        # associated invoice
        invoice_item_aggregates = (
            InvoiceItem.objects.filter(invoice_id__in=invoice_ids)
            .values('invoice_id')
            .annotate(
                grossTotal=Coalesce(Sum('grossTotal'), 0, output_field=FloatField()),
                total=Coalesce(Sum('total'), 0, output_field=FloatField()),
                adjustments=Coalesce(Sum('adjustments'), 0, output_field=FloatField()),
                taxes=Coalesce(Sum('taxes'), 0, output_field=FloatField()),
                fees=Coalesce(Sum('fees'), 0, output_field=FloatField()),
            )
        )

        # Build a lookup dict keyed by invoice_id
        invoice_details_by_invoice = {
            row['invoice_id']: row for row in invoice_item_aggregates
        }

        extras_dict = {x.id: [] for x in registrations}

        if registrations:
            extras = get_eventregistration_data.send(
                sender=EventRegistrationSummaryView,
                eventregistrations=[x.id for x in registrations]
            )
            for k, v in chain.from_iterable([x.items() for x in [y[1] for y in extras if y[1]]]):
                extras_dict[k].extend(v)

        # Call the signal that gets additional names and append them into a single
        # list.
        if getConstant('registration__addGuestListToViewRegistrations'):
            name_response = get_additional_event_names.send(
                sender=EventRegistrationSummaryView, event=self.object
            )
            additional_names = []
            for r in name_response:
                if len(r) > 1:
                    additional_names += list(r[1])
        else:
            additional_names = []

        additional_names_extras_dict = {x.get('contact'): [] for x in additional_names if x.get('contact')}

        if additional_names:
            extra_names_data = get_person_data.send(
                sender=EventRegistrationSummaryView,
                names=additional_names,
            )
            for k, v in chain.from_iterable([x.items() for x in [y[1] for y in extra_names_data if y[1]]]):
                additional_names_extras_dict[k].extend(v)

        context = {
            'event': self.object,
            'next_occurrence': self.object.nextOccurrenceForToday,
            'registrations': registrations,
            'invoice_details': {
                reg.id: invoice_details_by_invoice.get(reg.registration.invoice_id, {})
                for reg in registrations
            },
            'additional_names': additional_names,
            'extras': extras_dict,
            'additional_names_extras': additional_names_extras_dict,
            'extras_templates_registry': extras_templates_registry,
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

        # Reduce DB calls
        querylist = list(queryset)

        # These are all the various attributes that we want to be populated in the response JSON
        attributeList = [
            'id', 'dropIn', 'refundFlag', 'warningFlag',
            'checkedIn', 'occurrenceId', 'occurrenceStartTime', 'student',
            ('customer', ['id', 'fullName', 'email', 'numClassSeries']),
            ('event', ['id', 'name', 'url',]),
            ('registration', [
                'id', 'refundFlag', 'grossTotal', 'total', 'discounted', 'url',
                ('invoice', [
                    'id', 'grossTotal', 'total', 'adjustments', 'taxes', 'fees',
                    'outstandingBalance', 'statusLabel', 'url'
                ]),
            ]),
            ('invoiceItem', [
                'id', 'grossTotal', 'total', 'adjustments', 'taxes', 'fees',
                'revenueMismatch', 'revenueNotYetReceived', 'revenueReceived',
                'revenueReported'
            ]),
            ('role', ['id', 'name']),
        ]

        extras_dict = {}

        if querylist:
            extras = get_eventregistration_data.send(
                sender=EventRegistrationJsonView,
                eventregistrations=[x.id for x in querylist]
            )
            extras_dict = {x.id: [] for x in querylist}
            for k, v in chain.from_iterable([
                x.items() for x in [y[1] for y in extras if isinstance(y[1], dict)]
            ]):
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
            filters['customer'] = self.customer

        dropInFilters = Q(dropIn=False) | (Q(dropIn=True) & Q(occurrences__id=F('occurrenceId')))

        registrations = EventRegistration.objects.filter(
            **filters
        ).annotate(
            occurrenceId=F('event__eventoccurrence__id'),
            occurrenceStartTime=F('event__eventoccurrence__startTime'),
        ).filter(dropInFilters).select_related(
            'registration', 'event', 'customer',
            'invoiceItem', 'role', 'registration__invoice',
        ).order_by('customer__first_name', 'customer__last_name')
        return registrations
