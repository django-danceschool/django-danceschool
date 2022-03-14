from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.http import Http404, JsonResponse
from django.core.exceptions import ObjectDoesNotExist

from braces.views import PermissionRequiredMixin
from datetime import datetime
import json
import logging

from .models import GuestList, Event, GuestListName
from danceschool.core.utils.timezone import ensure_localtime
from danceschool.core.models import EventCheckIn, Registration, StaffMember
from danceschool.core.signals import get_person_data

# Define logger for this file
logger = logging.getLogger(__name__)


class GuestListView(PermissionRequiredMixin, TemplateView):
    '''
    This view is used to access the guest list for a given series or event
    '''
    template_name = 'guestlist/guestlist.html'
    permission_required = 'guestlist.view_guestlist'
    event = None
    guest_list = None
    date = None

    def dispatch(self, request, *args, **kwargs):
        try:
            self.date = datetime.strptime(request.GET.get('date') or '', '%Y-%m-%d')
        except ValueError:
            self.date = None

        self.guest_list = GuestList.objects.filter(
            id=self.kwargs.get('guestlist_id', None)).first()
        self.event = Event.objects.filter(
            id=self.kwargs.get('event_id', None)
        ).first() or getattr(self.guest_list, 'currentEvent', None)

        if (
            self.guest_list and self.event and not
            self.guest_list.appliesToEvent(self.event)
        ):
            raise Http404(_('Invalid event.'))

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ''' Add the list of names for the given guest list '''

        context = {
            'guestList': self.guest_list,
            'event': self.event,
            'date': self.date,
            'names': self.guest_list.getListForEvent(self.event),
        }
        context.update(kwargs)
        return super(GuestListView, self).get_context_data(**context)


class GuestListJsonView(GuestListView):
    '''
    This view provides the guest list in JSON format.
    '''
    template_name = None

    def render_to_response(self, context, **response_kwargs):
        json_context = {
            'names': context.get('names'),
            'guestlist_id': getattr(context.get('guestList'), 'id'),
            'event_id': getattr(context.get('event'), 'id'),
        }

        return JsonResponse(json_context)


class GuestCheckInfoJsonView(PermissionRequiredMixin, View):
    '''
    Provide check-in status information for a specific GuestList-provided name
    for a specified set of events.
    '''

    permission_required = 'guestlist.checkin_guests'

    def post(self, request, *args, **kwargs):
        '''
        Parse the information that is passed. POST data must include the following
        parameters: ['eventList', 'guestListId', 'modelType', 'id',].  It may optionally
        include: ['checkInType', 'date',].
        '''

        try:
            post_data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError:
            return JsonResponse({'code': 'invalid_json', 'message': _('Invalid JSON.')})

        event_list = post_data.get('eventList', [])
        event_list = Event.objects.filter(id__in=list(filter(lambda x: x.isdigit(), event_list)))

        if not event_list:
            return JsonResponse({
                'code': 'no_event_list', 'message': _('No event list specified.')
            })

        if (not post_data.get('guestListId', None)):
            return JsonResponse({
                'code': 'no_guest_list', 'message': _('No guest list specified.')
            })

        try:
            this_list = GuestList.objects.get(id=post_data['guestListId'])
        except ObjectDoesNotExist:
            return JsonResponse({
                'code': 'invalid_guest_list', 'message': _('Invalid guest list specified.')
            })

        if post_data.get('date', None):
            try:
                date = ensure_localtime(datetime.strptime(post_data.get('date', ''), '%Y-%m-%d')).date()
            except ValueError:
                return JsonResponse({
                    'code': 'invalid_date', 'message': _('Invalid date passed')
                })
        else:
            date = ensure_localtime(timezone.now()).date()

        if (
            post_data.get('modelType', None) not in
            ['GuestListName', 'StaffMember', 'Registration'] or not
            post_data.get('id', None)
        ):
            return JsonResponse({
                'code': 'invalid_guest_type',
                'message': _('Invalid guest type or no ID passed.')
            })

        try:
            if post_data['modelType'] == 'GuestListName':
                this_item = GuestListName.objects.get(id=post_data['id'])
                this_first_name = this_item.firstName
                this_last_name = this_item.lastName
                this_email = this_item.email
            elif post_data['modelType'] == 'StaffMember':
                this_item = StaffMember.objects.get(id=post_data['id'])
                this_first_name = this_item.firstName
                this_last_name = this_item.lastName
                this_email = (
                    this_item.privateEmail or
                    getattr(this_item.userAccount, 'email', None) or
                    this_item.publicEmail
                )
            elif post_data['modelType'] == 'Registration':
                this_item = Registration.objects.get(id=post_data['id'])
                this_first_name = this_item.invoice.firstName
                this_last_name = this_item.invoice.lastName
                this_email = this_item.invoice.email
        except ObjectDoesNotExist:
            return JsonResponse({
                'code': 'guest_not_found', 'message': _('Guest not found.')
            })

        # Confirm that the name is actually on the guest list.  Names are not
        # event-specific (staff and registrations are).
        if (
            post_data['modelType'] == 'GuestListName' and
            this_item.guestList != this_list
        ):
            return JsonResponse({
                'code': 'invalid_guest',
                'message': _('Invalid guest.')
            })

        extras_response = []
        extra_person_data = get_person_data.send(
            sender=GuestCheckInfoJsonView, first_name=this_first_name,
            last_name=this_last_name, email=this_email
        )
        for item in extra_person_data:
            if len(item) > 1 and isinstance(item[1], dict) and item[1]:
                extras_response.append(item[1])

        # Since we got this far, generate a response
        response = {'status': 'success', 'events': []}

        # Only report check-in status for the events that apply to this
        # StaffMember:
        if not (
            (not this_list.appliesToEvents(event_list)) or
            (
                post_data['modelType'] == 'StaffMember' and not
                this_list.getStaffForEvents(event_list).filter(id=post_data['id'])
            ) or
            (
                post_data['modelType'] == 'Registration' and not
                this_item.eventregistration_set.filter(event__in=event_list).exists()
            )
        ):
            for event in event_list:

                # Look for an existing event check-in
                filters = {
                    'event': event, 'eventRegistration__isnull': True,
                    'checkInType': post_data.get('checkInType', 'O'),
                    'firstName': this_first_name,
                    'lastName': this_last_name,
                    'cancelled': False,
                }

                if post_data.get('checkInType', 'O') == "O":
                    this_occurrence = post_data.get(
                        'occurrence', event.getNextOccurrenceForDate(date=date)
                    )
                    filters['occurrence'] = this_occurrence
                else:
                    this_occurrence = None

                response['events'].append({
                    'id': this_item.id,
                    'modelType': post_data['modelType'],
                    'firstName': this_first_name,
                    'lastName': this_last_name,
                    'email': this_email,
                    'extras': extras_response,
                    'eventId': event.id, 'eventName': event.name,
                    'checkedIn': EventCheckIn.objects.filter(**filters).exists(),
                    'occurrenceId': this_occurrence.id,
                    'checkInType':  post_data.get('checkInType', 'O'),
                    'guestType': this_list.getDescriptionForGuest(this_item, event),
                })

        return JsonResponse(response)
