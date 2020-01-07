from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView
from django.shortcuts import get_object_or_404
from django.http import Http404, JsonResponse

from braces.views import PermissionRequiredMixin
from datetime import datetime

from .models import GuestList, Event


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
            self.date = datetime.strptime(request.GET.get('date') or '','%Y-%m-%d')
        except ValueError:
            self.date = None

        self.guest_list = GuestList.objects.filter(
            id=self.kwargs.get('guestlist_id', None)).first()
        self.event = Event.objects.filter(
            id=self.kwargs.get('event_id',None)).first() or \
                getattr(self.guest_list, 'currentEvent', None)

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
