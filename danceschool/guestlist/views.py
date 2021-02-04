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

        if not post_data.get('eventList', None):
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
            elif post_data['modelType'] == 'StaffMember':
                this_item = StaffMember.objects.get(id=post_data['id'])
            elif post_data['modelType'] == 'Registration':
                this_item = Registration.objects.get(id=post_data['id'])
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

        # Since we got this far, generate a response
        response = {'status': 'success', 'events': []}

        for event in Event.objects.filter(id__in=post_data.get('eventList', [])):

            # Only report check-in status for the events that apply to this
            # StaffMember:
            if (
                (not this_list.appliesToEvent(event)) or
                (
                    post_data['modelType'] == 'StaffMember' and not
                    this_list.getStaffForEvent(event).filter(id=post_data['id'])
                ) or
                (
                    post_data['modelType'] == 'Registration' and not
                    this_item.eventregistration_set.filter(event=event).exists()
                )
            ):
                continue

            # Look for an existing event check-in
            filters = {
                'event': event, 'eventRegistration__isnull': True,
                'checkInType': post_data.get('checkInType', 'O'),
                'firstName': this_item.firstName,
                'lastName': this_item.lastName,
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
                'firstName': this_item.firstName,
                'lastName': this_item.lastName,
                'eventId': event.id, 'eventName': event.name,
                'checkedIn': EventCheckIn.objects.filter(**filters).exists(),
                'occurrenceId': this_occurrence.id,
                'checkInType':  post_data.get('checkInType', 'O'),
                'guestType': this_list.getDescriptionForGuest(this_item, event),
            })

        return JsonResponse(response)
