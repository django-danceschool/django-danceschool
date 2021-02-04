from django.http import HttpResponse, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q, Value
from django.db.models.functions import Concat

from braces.views import PermissionRequiredMixin
import json

from .models import (
    Event, EventOccurrence, SeriesTeacher, EventRegistration, EmailTemplate,
    EventCheckIn
)


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
        series_option = request.POST.get('event') or None
        seriesClasses = EventOccurrence.objects.filter(event__id=series_option)
        seriesTeachers = SeriesTeacher.objects.filter(event__id=series_option)
    else:
        # Only return attributes for valid requests
        return JsonResponse({})

    outClasses = {}
    for option in seriesClasses:
        outClasses[str(option.id)] = option.__str__()

    outTeachers = {}
    for option in seriesTeachers:
        outTeachers[str(option.id)] = option.__str__()

    return JsonResponse({
        'id_occurrences': outClasses,
        'id_replacedStaffMember': outTeachers,
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
        event_id = post_data.get('event_id')
        checkin_type = post_data.get('checkin_type')
        occurrence_id = post_data.get('occurrence_id')
        registrations = post_data.get('registrations', [])
        names = post_data.get('names', [])

        if requested not in ['get', 'get_all', 'update']:
            errors.append({
                'code': 'invalid_request',
                'message': _(
                    'Invalid request type. ' +
                    'Options are \'get\', \'get_all\', and \'update\'.'
                )
            })

        if not event_id:
            errors.append({
                'code': 'no_event',
                'message': _('No event specified.')
            })
            return self.errorResponse(errors)

        this_event = Event.objects.filter(id=event_id).prefetch_related(
            'eventoccurrence_set', 'eventregistration_set', 'eventcheckin_set',
            'eventregistration_set__registration'
        ).first()

        if not this_event:
            errors.append({
                'code': 'invalid_event',
                'message': _('Invalid event specified.')
            })
            return self.errorResponse(errors)

        if checkin_type not in ['E', 'O']:
            errors.append({
                'code': 'invalid_checkin_type',
                'message': _('Invalid check-in type.'),
            })

        if checkin_type == 'O':
            this_occurrence = this_event.eventoccurrence_set.filter(
                id=occurrence_id
            ).first()
            if not this_occurrence:
                errors.append({
                    'code': 'invalid_occurrence',
                    'message': _('Invalid event occurrence.'),
                })
        else:
            this_occurrence = None

        if registrations:
            these_registrations = this_event.eventregistration_set.filter(
                id__in=[x.get('id') for x in registrations],
                registration__final=True,
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
        existing_checkins = EventCheckIn.objects.filter(
            event=this_event, checkInType=checkin_type,
            occurrence=this_occurrence,
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
        new_checkins = [
            EventCheckIn(
                event=this_event, checkInType=checkin_type,
                occurrence=this_occurrence,
                eventRegistration=this_event.eventregistration_set.get(id=x.get('id')),
                cancelled=x.get('cancelled', False),
                firstName=this_event.eventregistration_set.get(id=x.get('id')).registration.firstName,
                lastName=this_event.eventregistration_set.get(id=x.get('id')).registration.lastName,
                submissionUser=submissionUser,
            ) for x in registrations
        ] + [
            EventCheckIn(
                event=this_event, checkInType=checkin_type,
                occurrence=this_occurrence,
                cancelled=x.get('cancelled', False),
                firstName=x.get('first_name'),
                lastName=x.get('last_name'),
                submissionUser=submissionUser,
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
