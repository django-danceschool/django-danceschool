from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import DetailView, View
from django.contrib.auth.mixins import AccessMixin
from django.db.models import Q, F, Value, Case, When, DateTimeField, Min, Max
from django.db.models.functions import Concat
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from itertools import chain
from braces.views import PermissionRequiredMixin
import json
import qrcode
from io import BytesIO

from ..models import (
    Invoice, EventRegistration, EventCheckIn, Event
)
from ..signals import get_eventregistration_data
from ..registries import extras_templates_registry
from ..utils.timezone import ensure_localtime

import logging

logger = logging.getLogger(__name__)


class CustomerSingleCheckInView(AccessMixin, DetailView):
    '''
    This view can be sent to customers (e.g. in a registration email).  It
    allows them to present a QR code at the door for quicker check-in.
    '''
    template_name = 'core/customer_single_checkin.html'

    def get_object(self, queryset=None):
        return get_object_or_404(
            Invoice.objects.filter(
                id=self.kwargs.get('invoice_id')
            ).select_related('registration')
        )

    def get(self, request, *args, **kwargs):
        '''
        Registrations can be viewed only if the validation string is provided
        along with the invoice ID, unless the user is logged in and has
        view_all_invoice permissions
        '''
        self.object = self.get_object()
        user_has_permissions = request.user.has_perm('core.view_all_invoices')
        user_has_validation_string = (
            request.GET.get('v', None) == self.object.validationString or
            self.kwargs.get('validation_string') == self.object.validationString
        )

        if user_has_validation_string or user_has_permissions:
            context = self.get_context_data(
                object=self.object,
                user_has_permissions=user_has_permissions,
                user_has_validation_string=user_has_validation_string,
            )

            if self.object.registration:
                context['qrcode_url'] = request.build_absolute_uri(
                    reverse(
                        'customer_qrcode_validated',
                        args=(self.object.id, self.object.validationString)
                    )
                )

            return self.render_to_response(context)
        return self.handle_no_permission()


class CustomerQrCodeView(AccessMixin, DetailView):
    ''' This class returns the QR code PNG '''

    def get_object(self, queryset=None):
        return get_object_or_404(
            Invoice.objects.filter(
                id=self.kwargs.get('invoice_id')
            ).select_related('registration')
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        user_has_permissions = request.user.has_perm('core.view_all_invoices')
        user_has_validation_string = (
            request.GET.get('v', None) == self.object.validationString or
            self.kwargs.get('validation_string') == self.object.validationString
        )

        if (user_has_validation_string or user_has_permissions):
            checkin_url = request.build_absolute_uri(reverse(
                'school_checkin', args=(self.object.id, )
            ))
            img = qrcode.make(checkin_url, box_size=20)
            stream = BytesIO()
            img.save(stream)
            return HttpResponse(stream.getvalue(), content_type='image/png')
        return self.handle_no_permission()


class SchoolSingleCheckInView(PermissionRequiredMixin, DetailView):
    '''
    This view is generally accessed by scanning a QR code.  It provides a list
    similar to the EventRegistrationSummaryView, but for which the scope of
    check-in options is all the event registrations associated with an invoice,
    rather than all those associated with an event.
    '''
    permission_required = 'core.view_registration_summary'
    template_name = 'core/view_eventregistrations.html'
    model = Invoice

    def get_context_data(self, **kwargs):
        ''' Add the list of event registrations for the given invoice. '''

        registrations = list(EventRegistration.objects.filter(
            registration__invoice=self.object, cancelled=False,
            registration__final=True,
        ).select_related(
            'registration', 'event', 'customer',
            'invoiceItem', 'role', 'registration__invoice',
        ).order_by(
            F('customer__last_name').asc(nulls_last=True),
            F('customer__first_name').asc(nulls_last=True),
        ))

        extras_dict = {x.id: [] for x in registrations}

        if registrations:
            extras = get_eventregistration_data.send(
                sender=SchoolSingleCheckInView,
                eventregistrations=[x.id for x in registrations]
            )
            for k, v in chain.from_iterable([x.items() for x in [y[1] for y in extras if y[1]]]):
                extras_dict[k].extend(v)

        context = {
            'scope': 'invoice',
            'invoice': self.object,
            'registrations': registrations,
            'extras': extras_dict,
            'extras_templates_registry': extras_templates_registry,
        }
        context.update(kwargs)
        return super().get_context_data(**context)


class ProcessCheckInView(PermissionRequiredMixin, View):
    permission_required = 'core.checkin_customers'

    def errorResponse(self, errors):
        ''' Return a formatted error response. Takes a dict of errors. '''

        return JsonResponse({
            'status': 'failure',
            'errors': errors,
        })

    def post(self, request, *args, **kwargs):
        '''
        Handle creation or update of EventCheckIn instances associated with
        the passed set of registrations.
        '''

        errors = []

        if request.user.is_authenticated:
            submissionUser = request.user
        else:
            submissionUser = None

        try:
            post_data = json.loads(request.body)
        except json.decoder.JSONDecodeError:
            errors.append({
                'code': 'invalid_json',
                'message': _('Invalid JSON.')
            })
            return self.errorResponse(errors)

        requested = post_data.get('request')
        scope = post_data.get('scope', 'event')
        event_id = post_data.get('event_id')
        invoice_id = post_data.get('invoice_id')

        checkin_type = post_data.get('checkin_type')
        occurrence_id = post_data.get('occurrence_id')
        registrations = post_data.get('registrations', [])
        names = post_data.get('names', [])

        # Initialize event, invoice, and occurrence for easier logic.
        this_event = None
        this_invoice = None
        this_occurrence = None

        if requested not in ['get', 'get_all', 'update']:
            errors.append({
                'code': 'invalid_request',
                'message': _(
                    'Invalid request type. ' +
                    'Options are \'get\', \'get_all\', and \'update\'.'
                )
            })

        if scope == 'event' and not event_id:
            errors.append({
                'code': 'no_event',
                'message': _('No event specified.')
            })
            return self.errorResponse(errors)
        elif scope == 'invoice' and not invoice_id:
            errors.append({
                'code': 'no_invoice',
                'message': _('No invoice specified.')
            })
        elif scope not in ['event', 'invoice']:
            errors.append({
                'code': 'invalid_scope',
                'message': _(
                    'Invalid scope. Options are \'event\' and \'invoice\'.'
                )
            })

        if checkin_type not in ['E', 'O']:
            errors.append({
                'code': 'invalid_checkin_type',
                'message': _('Invalid check-in type.'),
            })

        if errors:
            return self.errorResponse(errors)

        if scope == 'event':
            this_event = Event.objects.filter(id=event_id).prefetch_related(
                'eventoccurrence_set', 'eventregistration_set', 'eventcheckin_set',
                'eventregistration_set__registration', 'eventregistration_set__customer',
            ).first()

            if not this_event:
                errors.append({
                    'code': 'invalid_event',
                    'message': _('Invalid event specified.')
                })
            elif checkin_type == 'O':
                this_occurrence = this_event.eventoccurrence_set.filter(
                    id=occurrence_id
                ).first()
                if not this_occurrence:
                    errors.append({
                        'code': 'invalid_occurrence',
                        'message': _('Invalid event occurrence.'),
                    })

        if scope == 'invoice':
            this_invoice = Invoice.objects.filter(id=invoice_id).select_related(
                'registration',
            ).prefetch_related(
                'invoiceitem_set', 'invoiceitem_set__eventRegistration',
                'invoiceitem_set__eventRegistration__event',
                'invoiceitem_set__eventRegistration__customer',
            ).first()

            if not this_invoice:
                errors.append({
                    'code': 'invalid_invoice',
                    'message': _('Invalid invoice specified.')
                })

        if errors:
            return self.errorResponse(errors)

        if registrations:
            er_filters = (
                Q(id__in=[x.get('id') for x in registrations]) &
                Q(registration__final=True)
            )

            if this_event:
                er_filters = er_filters & Q(event=this_event)

            if this_invoice:
                er_filters = er_filters & Q(registration__invoice=this_invoice)

            these_registrations = EventRegistration.objects.filter(
                er_filters
            ).select_related('event', 'customer', 'registration').prefetch_related(
                'event__eventoccurrence_set'
            )

            if these_registrations.count() < len(registrations):
                errors.append({
                    'code': 'invalid_registrations',
                    'message': _('Invalid event registration IDs.'),
                })
        else:
            these_registrations = EventRegistration.objects.none()

        these_full_names = [
            ' '.join([x.get('first_name', ''), x.get('last_name', '')]).strip()
            for x in names
        ]

        if '' in these_full_names:
            errors.append({
                'code': 'invalid_name',
                'message': _('Cannot process check in for an empty name.')
            })

        if errors:
            return self.errorResponse(errors)

        # Get the set of existing check-ins that need to be returned or updated.
        checkin_filters = Q(checkInType=checkin_type)
        annotations = {}

        if scope == 'event':
            checkin_filters = checkin_filters & Q(event=this_event)

            if checkin_type == 'O':
                checkin_filters = checkin_filters & Q(occurrence=this_occurrence)

        elif scope == 'invoice':
            checkin_filters = checkin_filters & Q(eventRegistration__invoiceItem__invoice=this_invoice)

            if checkin_type == 'O':
                annotations = {
                    'future': Case(When(
                        occurrence__startTime__gte=ensure_localtime(timezone.now()).replace(
                            hour=0, minute=0, second=0
                        ), then=F('occurrence__startTime')
                    ), default=None, output_field=DateTimeField()),
                    'min_startTime': Min('future'),
                    'max_startTime': Max('occurrence__startTime'),
                }
                checkin_filters = (
                    checkin_filters &
                    Q(eventRegistration__registration__invoice=this_invoice) &
                    (Q(future=F('min_startTime')) | (
                        Q(min_startTime__isnull=True) & Q(occurrence__startTime=F('max_startTime'))
                    ))
                )

        existing_checkins = EventCheckIn.objects.annotate(**annotations).filter(
            checkin_filters
        ).select_related('eventRegistration')

        if requested != 'get_all':
            existing_checkins = existing_checkins.annotate(
                dbFullName=Concat('firstName', Value(' '), 'lastName')
            ).filter(
                Q(eventRegistration__in=these_registrations) |
                Q(
                    Q(eventRegistration__isnull=True) &
                    Q(dbFullName__in=these_full_names)
                )
            )

        # We pass along all info if requested except submissionUsers and JSON
        # data.
        if requested in ['get', 'get_all']:
            return JsonResponse({
                'status': 'success',
                'checkins': [
                    {
                        'id': x.id,
                        'event': x.event_id,
                        'occurrence': x.occurrence_id,
                        'checkInType': x.checkInType,
                        'eventRegistration': x.eventRegistration_id,
                        'cancelled': x.cancelled,
                        'firstName': x.firstName,
                        'lastName': x.lastName,
                        'creationDate': x.creationDate,
                        'modifiedDate': x.modifiedDate,
                    }
                    for x in existing_checkins
                ]
            })

        # If we get to here, then this is an update request.
        # Set the attributes for EventCheckIns that need to be updated while
        # also filtering the set of registrations and names for which new
        # check-ins need to be created.

        for checkin in existing_checkins:
            if checkin.eventRegistration:
                this_update = [
                    x for x in registrations if
                    int(x.get('id')) == checkin.eventRegistration.id
                ]
                if len(this_update) > 1 or len(this_update) == 0:
                    errors.append({
                        'code': 'invalid_registrations',
                        'message': _('Invalid event registration IDs.'),
                    })
                    return self.errorResponse(errors)
                registrations.remove(this_update[0])
            else:
                this_update = [
                    x for x in names if
                    x.get('first_name') == checkin.firstName and
                    x.get('last_name') == checkin.lastName
                ]
                if len(this_update) > 1 or len(this_update) == 0:
                    errors.append({
                        'code': 'invalid_names',
                        'message': _('Invalid or duplicated names.'),
                    })
                    return self.errorResponse(errors)
                names.remove(this_update[0])

            checkin.submissionUser = submissionUser
            checkin.cancelled = this_update[0].get('cancelled', False)

        EventCheckIn.objects.bulk_update(
            existing_checkins, ['cancelled', 'submissionUser']
        )

        # Create EventCheckIns associated with remaining new registrations and
        # names.
        new_checkins = []
        new_checkin_kwargs = {
            'checkInType': checkin_type,
            'submissionUser': submissionUser,
        }
        if scope == "event":
            new_checkin_kwargs.update({
                'event': this_event,
                'occurrence': this_occurrence
            })

        for x in registrations:
            this_checkin_reg = these_registrations.get(id=x.get('id'))

            this_checkin_kwargs = {
                'eventRegistration': this_checkin_reg,
                'cancelled': x.get('cancelled', False),
                'firstName': getattr(this_checkin_reg.customer, 'first_name', None),
                'lastName': getattr(this_checkin_reg.customer, 'last_name', None),
            }

            if scope == 'invoice':
                this_checkin_kwargs['event'] = this_checkin_reg.event
                this_checkin_kwargs['occurrence'] = (
                    this_checkin_reg.event.nextOccurrenceForToday or
                    this_checkin_reg.event.lastOccurrence
                )

            new_checkins.append(EventCheckIn(
                **this_checkin_kwargs, **new_checkin_kwargs
            ))

        new_checkins += [
            EventCheckIn(
                cancelled=x.get('cancelled', False),
                firstName=x.get('first_name'),
                lastName=x.get('last_name'),
                **new_checkin_kwargs
            ) for x in names
        ]

        EventCheckIn.objects.bulk_create(new_checkins)

        return JsonResponse({
            'status': 'success',
            'updated': len(existing_checkins),
            'created': len(new_checkins),
        })
