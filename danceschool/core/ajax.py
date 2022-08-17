from django.http import HttpResponse, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q, Value, Case, When, F, DateTimeField, Min, Max
from django.db.models.functions import Concat

from braces.views import PermissionRequiredMixin
import json

from .models import (
    Event, EventOccurrence, EventStaffMember, EventRegistration, EmailTemplate,
    EventCheckIn, Invoice
)
from .utils.timezone import ensure_localtime
from .constants import getConstant


class UserAccountInfo(View):
    ''' This view just returns the name and email address information for the currently logged in user '''

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        context = {}

        if not request.user.is_authenticated:
            return JsonResponse(context)

        customer = getattr(request.user, 'customer', None)

        if customer:
            context.update({
                'customer': True,
                'first_name': customer.first_name or request.user.first_name,
                'last_name': customer.last_name or request.user.last_name,
                'email': customer.email or request.user.email,
                'phone': customer.phone,
            })
        else:
            context.update({
                'customer': False,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
            })

        # Also add any outstanding messages (e.g. login successful message) to be
        # relayed to the user when this information is used.
        context['messages'] = []

        for message in messages.get_messages(request):
            context['messages'].append({
                "level": message.level,
                "message": message.message,
                "extra_tags": message.tags,
            })

        return JsonResponse(context)


def updateSeriesAttributes(request):
    '''
    This function handles the filtering of available series classes and seriesteachers when a series
    is chosen on the Substitute Teacher reporting form.
    '''
    if request.method == 'POST' and request.POST.get('event'):
        event_id = request.POST.get('event') or None
        occurrence_filters = Q(event__id=event_id)
        staff_filters = Q(event__id=event_id)
    else:
        # Only return attributes for valid requests
        return JsonResponse({})

    category_id = request.POST.get('category')
    if category_id == getConstant('general__eventStaffCategorySubstitute').id:
        staff_filters &= (
            Q(category__id=getConstant('general__eventStaffCategoryInstructor')) | 
            Q(category__id=getConstant('general__eventStaffCategoryAssistant'))
        )
    elif category_id:
        staff_filters &= Q(category__id=category_id)

    occurrence_ids = request.POST.get('occurrences')
    if occurrence_ids:
        occurrence_filters &= Q(id__in=occurrence_ids)
        # The staff members must match all occurrences.
        for occ in occurrence_ids:
            staff_filters &= Q(occurrences=occ)
    else:
        # Don't return staff unless occurrences are specified.
        staff_filters = Q(pk__in=[])

    outOccurrences = {}
    for option in EventOccurrence.objects.filter(occurrence_filters):
        outOccurrences[str(option.id)] = option.__str__()

    outStaff = {}
    for option in EventStaffMember.objects.filter(staff_filters):
        outStaff[str(option.id)] = option.__str__()

    return JsonResponse({
        'id_occurrences': outOccurrences,
        'id_replacedStaffMember': outStaff,
    })


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
                        'event': x.event.id,
                        'occurrence': getattr(x.occurrence, 'id', None),
                        'checkInType': x.checkInType,
                        'eventRegistration': getattr(x.eventRegistration, 'id', None),
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
